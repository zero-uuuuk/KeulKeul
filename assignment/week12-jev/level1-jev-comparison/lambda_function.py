import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

OPENAI_URL = "https://api.openai.com/v1/responses"
JEV_URL = "https://api.typesafe.ai/v1/systemone"

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-terra")
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")

# 1M token 당 USD (조사 시점 기준 공개 가격)
TERRA_PRICE = {"input": 2.00, "output": 12.00}
JEV_PRICE = {"input": 0.042, "output": 0.0}

DEPARTMENTS = {
    "billing": "charges, invoices, refunds",
    "shipping": "delivery, tracking",
    "technical": "bugs, errors, how-to",
}
URGENCY_LEVELS = ["low", "medium", "high"]


def post_json(url, api_key, body):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read())


def cost_usd(usage, price):
    return round(
        (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1_000_000,
        8,
    )


def call_terra(message):
    schema = {
        "type": "object",
        "properties": {
            "department": {"type": "string", "enum": list(DEPARTMENTS)},
            "urgency": {"type": "string", "enum": URGENCY_LEVELS},
            "wants_refund": {"type": "boolean"},
        },
        "required": ["department", "urgency", "wants_refund"],
        "additionalProperties": False,
    }
    instructions = (
        "Classify the customer ticket. "
        f"department options: {json.dumps(DEPARTMENTS)}. "
        f"urgency options: {URGENCY_LEVELS}. "
        "wants_refund: whether the customer asks for money back."
    )
    body = {
        "model": OPENAI_MODEL,
        "instructions": instructions,
        "input": message,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ticket_decision",
                "strict": True,
                "schema": schema,
            }
        },
    }

    started = time.perf_counter()
    data = post_json(OPENAI_URL, os.environ["OPENAI_API_KEY"], body)
    latency_ms = round((time.perf_counter() - started) * 1000)

    text = next(
        part["text"]
        for item in data["output"]
        if item["type"] == "message"
        for part in item["content"]
        if part["type"] == "output_text"
    )
    return {
        "model": data.get("model", OPENAI_MODEL),
        "answer": json.loads(text),
        "latency_ms": latency_ms,
        "usage": data["usage"],
        "cost_usd": cost_usd(data["usage"], TERRA_PRICE),
    }


def call_jev(message):
    body = {
        "model": JEV_MODEL,
        "state": message,
        "questions": {
            "department": {
                "type": "choice",
                "instructions": "Which team handles this?",
                "criteria": DEPARTMENTS,
            },
            "urgency": {
                "type": "score",
                "instructions": "How urgent is this?",
                "criteria": URGENCY_LEVELS,
            },
            "wants_refund": {
                "type": "noul",
                "instructions": "Is the customer asking for money back?",
            },
        },
    }

    started = time.perf_counter()
    data = post_json(JEV_URL, os.environ["TYPESAFE_API_KEY"], body)
    latency_ms = round((time.perf_counter() - started) * 1000)

    answers = data["answers"]
    return {
        "model": data["model"],
        "answer": {
            "department": answers["department"]["choice"],
            "urgency": URGENCY_LEVELS[round(answers["urgency"]["score"])],
            "wants_refund": answers["wants_refund"]["noul"] >= 0.5,
        },
        "confidence": {
            "department": answers["department"]["confidence"],
            "urgency": answers["urgency"]["confidence"],
            "wants_refund_probability": answers["wants_refund"]["noul"],
        },
        "latency_ms": latency_ms,
        "usage": data["usage"],
        "cost_usd": cost_usd(data["usage"], JEV_PRICE),
    }


def safe_call(fn, message):
    try:
        return fn(message)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def get_message(event):
    if event.get("requestContext", {}).get("http", {}).get("method") == "POST" and event.get("body"):
        return json.loads(event["body"]).get("message")
    return (event.get("queryStringParameters") or {}).get("message")


def lambda_handler(event, context):
    message = get_message(event)
    if not message:
        return response(400, {"error": "message is required (POST JSON body or ?message=)"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        terra = pool.submit(safe_call, call_terra, message)
        jev = pool.submit(safe_call, call_jev, message)
        result = {
            "message": message,
            "request_id": context.aws_request_id,
            "terra": terra.result(),
            "jev": jev.result(),
        }
    return response(200, result)


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }
