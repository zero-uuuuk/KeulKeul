"""역할: API Gateway 요청을 받아 S3에 저장된 이미지 분류 결과 JSON을 반환한다.

상세 과정:
  1. query string의 key 값을 읽어 결과 JSON의 S3 key를 결정한다.
  2. key가 없으면 latest.json을 읽어 가장 최근 분류 결과를 반환한다.
  3. 결과 파일이 없거나 S3 조회가 실패하면 HTTP status code로 오류를 표현한다.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# 기본 설정 (S3)
# ---------------------------------------------------------------------------

RESULT_BUCKET = os.environ["RESULT_BUCKET"]
s3_client = boto3.client("s3")


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


def build_result_key(event: dict[str, Any]) -> str:
    """query string의 원본 이미지 key를 결과 JSON key로 변환한다."""

    # key를 생략하면 최신 결과를 반환해 첫 테스트 호출을 단순하게 만든다.
    query_params = event.get("queryStringParameters") or {}
    source_key = query_params.get("key")
    if not source_key:
        return "latest.json"

    return f"results/{source_key}.json"


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """S3 result bucket에서 분류 결과 JSON을 읽어 HTTP 응답으로 반환한다."""

    # API Gateway 요청 ID와 Lambda 요청 ID를 로그에 남겨 호출 흐름을 추적한다.
    result_key = build_result_key(event)
    request_id = getattr(context, "aws_request_id", "")
    print(f"분류 결과 조회: bucket={RESULT_BUCKET}, key={result_key}, request_id={request_id}")

    # 결과 JSON이 아직 없으면 업로드 후 Lambda 처리가 끝났는지 확인할 수 있게 404를 반환한다.
    try:
        response = s3_client.get_object(Bucket=RESULT_BUCKET, Key=result_key)
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code", "")
        if error_code in {"NoSuchKey", "404"}:
            return make_json_response(
                404,
                {
                    "error": "분류 결과를 찾을 수 없습니다.",
                    "result_key": result_key,
                    "request_id": request_id,
                },
            )
        raise

    # S3에 저장된 JSON을 그대로 반환하되 API 요청 ID를 덧붙인다.
    result_body = json.loads(response["Body"].read().decode("utf-8"))
    result_body["api_request_id"] = request_id
    return make_json_response(200, result_body)
