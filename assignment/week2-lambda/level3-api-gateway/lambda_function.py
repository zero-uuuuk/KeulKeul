"""역할: API Gateway HTTP API 요청을 route별 JSON 응답으로 변환한다.

상세 과정:
  1. API Gateway가 전달한 routeKey, method, path, query string, body를 event에서 읽는다.
  2. /health, /hello/{name}, /echo route를 각각 다른 응답으로 처리한다.
  3. 알 수 없는 route와 잘못된 JSON body는 명확한 HTTP status code로 반환한다.
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# HTTP 응답 생성
# ---------------------------------------------------------------------------

def make_json_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """API Gateway Lambda proxy integration 형식의 JSON 응답을 만든다."""

    # API Gateway는 문자열 body를 실제 HTTP 응답 본문으로 변환한다.
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def read_json_body(event: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """POST 요청 body를 JSON 객체로 파싱하고 실패하면 오류 메시지를 반환한다."""

    # body가 비어 있으면 빈 JSON 객체로 취급해 echo 요청을 단순하게 유지한다.
    raw_body = event.get("body")
    if not raw_body:
        return {}, None

    # 이번 실습은 일반 JSON 요청만 다루며 binary body는 처리하지 않는다.
    if event.get("isBase64Encoded"):
        return {}, "base64 body는 이번 실습에서 지원하지 않습니다."

    # JSON 문법이 잘못된 경우 400 응답을 만들 수 있도록 오류를 문자열로 반환한다.
    try:
        parsed_body = json.loads(raw_body)
    except json.JSONDecodeError:
        return {}, "요청 body가 올바른 JSON이 아닙니다."

    # 배열이나 문자열이 아니라 JSON 객체를 보내도록 제한해 응답 구조를 예측 가능하게 한다.
    if not isinstance(parsed_body, dict):
        return {}, "요청 body는 JSON 객체여야 합니다."

    return parsed_body, None


# ---------------------------------------------------------------------------
# Route 처리
# ---------------------------------------------------------------------------

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """API Gateway HTTP API 이벤트를 routeKey 기준으로 분기해 응답한다."""

    # payload format 2.0의 HTTP 메타데이터와 routeKey를 읽어 라우팅 기준으로 사용한다.
    route_key = event.get("routeKey", "$default")
    request_context = event.get("requestContext", {})
    http_context = request_context.get("http", {})

    # path parameter와 query string은 route별 응답을 만드는 입력값으로 사용한다.
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    request_id = getattr(context, "aws_request_id", "")

    # CloudWatch Logs에서 어떤 route가 어떤 Lambda 실행으로 처리됐는지 확인한다.
    print(
        f"API 요청: route={route_key}, method={http_context.get('method')}, "
        f"path={http_context.get('path')}, request_id={request_id}"
    )

    # 헬스 체크 route는 API와 Lambda 연결이 살아 있는지만 빠르게 확인한다.
    if route_key == "GET /health":
        return make_json_response(200, {"status": "ok", "request_id": request_id})

    # path parameter와 query string을 함께 사용해 동적 응답을 만든다.
    if route_key == "GET /hello/{name}":
        name = path_params.get("name", "Lambda")
        greeting = query_params.get("greeting", "Hello")
        return make_json_response(
            200,
            {
                "message": f"{greeting}, {name}",
                "name": name,
                "greeting": greeting,
                "request_id": request_id,
            },
        )

    # POST body를 JSON으로 읽어 클라이언트가 보낸 내용을 그대로 확인하게 한다.
    if route_key == "POST /echo":
        parsed_body, error_message = read_json_body(event)
        if error_message:
            return make_json_response(400, {"error": error_message, "request_id": request_id})

        return make_json_response(
            200,
            {
                "message": "echo",
                "body": parsed_body,
                "request_id": request_id,
            },
        )

    # $default route로 들어온 정의되지 않은 요청은 Lambda에서 404로 명확히 응답한다.
    return make_json_response(
        404,
        {
            "error": "지원하지 않는 route입니다.",
            "route": route_key,
            "path": http_context.get("path", ""),
            "request_id": request_id,
        },
    )
