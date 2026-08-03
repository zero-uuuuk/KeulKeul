"""역할: CloudWatch 실습용 Lambda API 응답과 구조화 로그를 생성한다.

상세 내용:
  1. query string의 mode 값에 따라 정상, 지연, 실패 응답을 만든다.
  2. 각 요청의 처리 결과를 JSON 로그로 출력해 Logs Insights에서 분석할 수 있게 한다.
  3. 애플리케이션 관점의 실패는 ERROR 로그로 남기되 Lambda runtime 예외와 구분한다.
"""

import json
import time
from typing import Any


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """API Gateway 요청을 처리하고 CloudWatch에서 분석할 구조화 로그를 남긴다."""
    started_at = time.perf_counter()
    query = event.get("queryStringParameters") or {}
    mode = query.get("mode", "ok")

    # mode 값에 따라 운영 실습용 응답 상태를 결정
    status_code = 200
    message = "정상 응답입니다."
    if mode == "slow":
        time.sleep(2)
        message = "느린 응답입니다."
    elif mode == "error":
        status_code = 500
        message = "의도적으로 만든 실패 응답입니다."
    elif mode not in {"ok", "slow", "error"}:
        status_code = 400
        message = "mode는 ok, slow, error 중 하나여야 합니다."

    # CloudWatch Logs Insights가 필드로 인식할 수 있도록 JSON 한 줄 로그를 출력
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    log_event = {
        "service": "keulkeul-cloudwatch-api",
        "level": "ERROR" if status_code >= 500 else "INFO",
        "requestId": context.aws_request_id,
        "mode": mode,
        "statusCode": status_code,
        "latencyMs": latency_ms,
    }
    print(json.dumps(log_event, ensure_ascii=False))

    # API Gateway HTTP API의 Lambda proxy 응답 형식으로 반환
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(
            {
                "message": message,
                "mode": mode,
                "statusCode": status_code,
                "latencyMs": latency_ms,
            },
            ensure_ascii=False,
        ),
    }
