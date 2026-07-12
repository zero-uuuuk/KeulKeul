"""DynamoDB club membership API for Lambda Function URL or HTTP API.

Supported requests:
  GET    /?title=president
  GET    /?user_id=younguk
  POST   / with JSON body
  PATCH  / with JSON body
  PUT    / with JSON body
  DELETE /?user_id=hyunryeo&todo_id=membership
"""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key


TABLE_NAME = os.environ.get("TABLE_NAME", "keulkeul-todos")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def json_default(value: Any) -> Any:
    """Convert DynamoDB Decimal values to JSON-safe numbers."""

    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build a Lambda proxy integration JSON response."""

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,PATCH,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(body, ensure_ascii=False, default=json_default),
    }


def get_method(event: dict[str, Any]) -> str:
    """Read the HTTP method from Function URL or API Gateway events."""

    return (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", "GET"))
    ).upper()


def get_query_params(event: dict[str, Any]) -> dict[str, str]:
    """Return query string parameters."""

    return event.get("queryStringParameters") or {}


def read_json_body(event: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Parse a JSON request body.

    Lambda console test events in this assignment use an object body for readability.
    Function URL requests usually pass body as a JSON string, so both formats work.
    """

    raw_body = event.get("body")
    if not raw_body:
        return {}, None

    if isinstance(raw_body, dict):
        return raw_body, None

    if event.get("isBase64Encoded"):
        return {}, "base64 body is not supported in this assignment"

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return {}, "request body must be valid JSON"

    if not isinstance(parsed, dict):
        return {}, "request body must be a JSON object"

    return parsed, None


def list_items(event: dict[str, Any]) -> dict[str, Any]:
    """List DynamoDB items by title or user_id."""

    query_params = get_query_params(event)
    title = query_params.get("title")

    if title:
        result = table.scan(FilterExpression=Attr("title").eq(title))

        return response(
            200,
            {
                "message": "items loaded",
                "title": title,
                "count": result.get("Count", 0),
                "items": result.get("Items", []),
            },
        )

    user_id = query_params.get("user_id", "younguk")
    result = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=True,
    )

    return response(
        200,
        {
            "message": "items loaded",
            "user_id": user_id,
            "count": result.get("Count", 0),
            "items": result.get("Items", []),
        },
    )


def build_item(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Convert the request payload into a DynamoDB item."""

    user_id = str(payload.get("user_id") or "").strip()
    todo_id = str(payload.get("todo_id") or "membership").strip()
    name = str(payload.get("name") or user_id).strip()
    title = str(payload.get("title") or "").strip()

    if not user_id:
        return {}, "user_id is required"

    if not title:
        return {}, "title is required"

    item = {
        "user_id": user_id,
        "todo_id": todo_id,
        "name": name,
        "title": title,
        "status": str(payload.get("status") or "active"),
        "created_at": str(payload.get("created_at") or int(time.time())),
    }

    return item, None


def create_item(event: dict[str, Any]) -> dict[str, Any]:
    """Create one or more DynamoDB items."""

    body, error_message = read_json_body(event)
    if error_message:
        return response(400, {"error": error_message})

    payloads = body.get("items")
    if payloads is None:
        payloads = [body]

    if not isinstance(payloads, list):
        return response(400, {"error": "items must be an array"})

    created_items = []
    for payload in payloads:
        if not isinstance(payload, dict):
            return response(400, {"error": "each item must be a JSON object"})

        if not payload.get("todo_id"):
            payload["todo_id"] = "membership"

        item, item_error = build_item(payload)
        if item_error:
            return response(400, {"error": item_error, "payload": payload})

        table.put_item(Item=item)
        created_items.append(item)

    return response(
        201,
        {
            "message": "items created",
            "count": len(created_items),
            "items": created_items,
        },
    )


def update_item(event: dict[str, Any]) -> dict[str, Any]:
    """Update the title, status, or name of a DynamoDB item."""

    body, error_message = read_json_body(event)
    if error_message:
        return response(400, {"error": error_message})

    user_id = body.get("user_id")
    todo_id = body.get("todo_id")

    if not user_id or not todo_id:
        return response(400, {"error": "user_id and todo_id are required"})

    allowed_fields = ("title", "status", "name")
    update_fields = {
        field: str(body[field])
        for field in allowed_fields
        if field in body and body[field] is not None
    }

    if not update_fields:
        return response(400, {"error": "one of title, status, or name is required"})

    expression_names = {"#updated_at": "updated_at"}
    expression_values = {":updated_at": str(int(time.time()))}
    set_expressions = ["#updated_at = :updated_at"]

    for field, value in update_fields.items():
        name_key = f"#{field}"
        value_key = f":{field}"
        expression_names[name_key] = field
        expression_values[value_key] = value
        set_expressions.append(f"{name_key} = {value_key}")

    result = table.update_item(
        Key={"user_id": str(user_id), "todo_id": str(todo_id)},
        UpdateExpression="SET " + ", ".join(set_expressions),
        ExpressionAttributeNames=expression_names,
        ExpressionAttributeValues=expression_values,
        ReturnValues="ALL_NEW",
    )

    return response(
        200,
        {
            "message": "item updated",
            "item": result.get("Attributes", {}),
        },
    )


def delete_item(event: dict[str, Any]) -> dict[str, Any]:
    """Delete a DynamoDB item."""

    query_params = get_query_params(event)
    user_id = query_params.get("user_id")
    todo_id = query_params.get("todo_id")

    if not user_id or not todo_id:
        return response(400, {"error": "query string user_id and todo_id are required"})

    table.delete_item(Key={"user_id": user_id, "todo_id": todo_id})

    return response(
        200,
        {
            "message": "item deleted",
            "user_id": user_id,
            "todo_id": todo_id,
        },
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Route each HTTP method to the matching DynamoDB operation."""

    method = get_method(event)
    path = event.get("rawPath") or event.get("path") or "/"
    request_id = getattr(context, "aws_request_id", "")

    print(f"request method={method}, path={path}, request_id={request_id}")

    if method == "OPTIONS":
        return response(200, {"message": "ok"})

    if method == "GET":
        return list_items(event)

    if method == "POST":
        return create_item(event)

    if method in {"PATCH", "PUT"}:
        return update_item(event)

    if method == "DELETE":
        return delete_item(event)

    return response(405, {"error": "method not allowed", "method": method})
