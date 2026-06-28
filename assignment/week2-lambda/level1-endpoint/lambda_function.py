"""역할: Lambda Function URL 실습용 HTTP 응답을 생성한다.

상세 과정:
  1. Function URL이 전달한 HTTP method, path, query string을 event에서 읽는다.
  2. name query parameter를 이용해 JSON 인사 응답을 만든다.
  3. Lambda 실행 정보와 요청 ID를 함께 반환해 CloudWatch Logs 관찰을 돕는다.
"""

from __future__ import annotations

import json
import time
from typing import Any


# ---------------------------------------------------------------------------
# HTTP 응답 생성
# ---------------------------------------------------------------------------

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda Function URL 요청을 받아 JSON HTTP 응답을 반환한다."""

    # Function URL payload format 2.0의 requestContext에서 HTTP 메타데이터를 읽는다.
    request_context = event.get("requestContext", {})
    http_context = request_context.get("http", {})

    # queryStringParameters가 없을 때도 같은 흐름으로 처리되도록 빈 딕셔너리를 사용한다.
    query_params = event.get("queryStringParameters") or {}
    name = query_params.get("name", "Lambda")

    # CloudWatch Logs에서 요청별 입력과 Lambda 요청 ID를 함께 확인할 수 있게 남긴다.
    request_id = getattr(context, "aws_request_id", "local-test")
    print(f"요청 처리: method={http_context.get('method')}, path={http_context.get('path')}, request_id={request_id}")

    # 브라우저와 curl 양쪽에서 바로 확인하기 쉬운 JSON 응답을 구성한다.
    body = {
        "message": f"Hello, {name}",
        "method": http_context.get("method", "GET"),
        "path": http_context.get("path", "/"),
        "request_id": request_id,
        "timestamp": int(time.time()),
    }

    # Function URL은 statusCode, headers, body 형태의 응답을 HTTP 응답으로 변환한다.
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }