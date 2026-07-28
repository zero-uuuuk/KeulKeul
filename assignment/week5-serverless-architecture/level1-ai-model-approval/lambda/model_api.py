"""역할: 모델 등록·조회·테스트 추론·Production 승인 API를 처리한다.

상세 과정:
  1. API Gateway HTTP API 이벤트에서 method, path, path parameter를 해석한다.
  2. 모델 metadata를 DynamoDB에 저장하고 S3 Presigned URL을 발급한다.
  3. 테스트 추론 Lambda를 호출한 뒤 결과를 DynamoDB item에 병합한다.
  4. 승인 조건을 확인하고 상태를 PRODUCTION으로 변경한 뒤 SNS 알림을 발행한다.
"""

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config


# ---------------------------------------------------------------------------
# AWS 클라이언트 및 환경 변수
# ---------------------------------------------------------------------------
TABLE_NAME = os.environ["TABLE_NAME"]
MODEL_BUCKET = os.environ["MODEL_BUCKET"]
APPROVAL_TOPIC_ARN = os.environ["APPROVAL_TOPIC_ARN"]
TEST_FUNCTION_NAME = os.environ["TEST_FUNCTION_NAME"]

table = boto3.resource("dynamodb").Table(TABLE_NAME)
s3_client = boto3.client(
    "s3",
    endpoint_url=f"https://s3.{os.environ['AWS_REGION']}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)
sns_client = boto3.client("sns")
lambda_client = boto3.client("lambda")


# ---------------------------------------------------------------------------
# 공통 변환 및 응답 유틸리티
# ---------------------------------------------------------------------------
def now_iso() -> str:
    """UTC 기준 ISO-8601 시간 문자열을 반환한다."""

    return datetime.now(timezone.utc).isoformat()


def response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """HTTP API Lambda proxy 응답 형식으로 JSON body를 감싼다."""

    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
            "Content-Type": "application/json",
        },
        "body": json.dumps(to_jsonable(body), ensure_ascii=False),
    }


def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    """API Gateway 이벤트의 JSON body를 dict로 파싱한다."""

    body = event.get("body") or "{}"
    return json.loads(body)


def to_decimal(value: Any) -> Any:
    """DynamoDB가 허용하지 않는 float 값을 Decimal로 재귀 변환한다."""

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [to_decimal(item) for item in value]
    if isinstance(value, dict):
        return {key: to_decimal(item) for key, item in value.items()}
    return value


def to_jsonable(value: Any) -> Any:
    """DynamoDB Decimal 값을 JSON 직렬화 가능한 int 또는 float로 재귀 변환한다."""

    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


def slug(value: str) -> str:
    """S3 key와 modelId에 안전하게 넣을 수 있는 소문자 문자열을 만든다."""

    normalized = value.strip().lower()
    return re.sub(r"[^a-z0-9._-]+", "-", normalized).strip("-")


# ---------------------------------------------------------------------------
# API 핸들러
# ---------------------------------------------------------------------------
def create_upload_url(event: dict[str, Any]) -> dict[str, Any]:
    """모델 metadata를 저장하고 ONNX 모델 업로드용 Presigned URL을 발급한다."""

    # 요청 body에서 모델 등록 정보를 읽고 S3 key에 안전한 값으로 정규화
    payload = parse_body(event)
    model_name = slug(payload["modelName"])
    version = slug(payload["version"])
    filename = slug(payload.get("filename") or "model.onnx")

    # 업로드된 모델을 나중에 modelId로 찾을 수 있게 S3 key 생성
    model_id = f"{model_name}-{version}"
    artifact_key = f"models/{model_name}/{version}/{filename}"
    timestamp = now_iso()

    # 업로드 전 상태를 DynamoDB에 먼저 저장
    item = {
        "modelId": model_id,
        "modelName": model_name,
        "version": version,
        "artifactKey": artifact_key,
        "accuracy": Decimal(str(payload["accuracy"])),
        "status": "PENDING_UPLOAD",
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    table.put_item(Item=item, ConditionExpression=Attr("modelId").not_exists())

    # 프론트엔드가 S3에 직접 PUT할 수 있는 Presigned URL 생성
    upload_url = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": MODEL_BUCKET,
            "Key": artifact_key,
            "ContentType": "application/octet-stream",
        },
        ExpiresIn=900,
    )

    return response(
        201,
        {
            "modelId": model_id,
            "uploadUrl": upload_url,
            "artifactKey": artifact_key,
        },
    )


def list_models() -> dict[str, Any]:
    """DynamoDB에 등록된 모델 후보 목록을 생성일 내림차순으로 반환한다."""

    items = sorted(table.scan().get("Items", []), key=lambda item: item.get("createdAt", ""), reverse=True)

    return response(200, {"items": items})


def run_test_inference(event: dict[str, Any]) -> dict[str, Any]:
    """후보 모델을 조회한 뒤 Test Inference Lambda 결과를 저장한다."""

    # 요청 대상 모델과 테스트 이미지 입력 확인
    model_id = event["pathParameters"]["modelId"]
    payload = parse_body(event)
    item = table.get_item(Key={"modelId": model_id}).get("Item")
    if not item:
        return response(404, {"message": "모델을 찾을 수 없습니다."})
    if item["status"] != "REVIEW":
        return response(409, {"message": "REVIEW 상태 모델만 테스트 추론할 수 있습니다."})
    if not payload.get("imageKey"):
        return response(400, {"message": "테스트 이미지 imageKey가 필요합니다."})

    # 추론 Lambda에 모델 위치와 테스트 이미지 위치 전달
    invoke_result = lambda_client.invoke(
        FunctionName=TEST_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(
            {
                "modelId": model_id,
                "modelBucket": MODEL_BUCKET,
                "artifactKey": item["artifactKey"],
                "imageKey": payload["imageKey"],
            }
        ).encode("utf-8"),
    )
    test_result = json.loads(invoke_result["Payload"].read())
    if invoke_result.get("FunctionError"):
        return response(
            502,
            {
                "message": test_result.get("errorMessage", "테스트 추론 Lambda 실행에 실패했습니다."),
                "detail": test_result,
            },
        )
    if not {"predictedLabel", "confidence", "latencyMs"}.issubset(test_result):
        return response(502, {"message": "테스트 추론 결과 형식이 올바르지 않습니다.", "detail": test_result})

    # 테스트 결과를 모델 item에 저장
    updated_at = now_iso()
    table.update_item(
        Key={"modelId": model_id},
        UpdateExpression="SET lastTestResult = :result, lastTestedAt = :tested_at, updatedAt = :updated_at",
        ExpressionAttributeValues={
            ":result": to_decimal(test_result),
            ":tested_at": updated_at,
            ":updated_at": updated_at,
        },
    )

    return response(200, test_result)


def create_test_image_url(event: dict[str, Any]) -> dict[str, Any]:
    """Reviewer가 테스트 이미지를 S3에 직접 올릴 수 있는 Presigned URL을 발급한다."""

    # 요청 대상 모델이 REVIEW 상태인지 확인
    model_id = event["pathParameters"]["modelId"]
    payload = parse_body(event)
    item = table.get_item(Key={"modelId": model_id}).get("Item")
    if not item:
        return response(404, {"message": "모델을 찾을 수 없습니다."})
    if item["status"] != "REVIEW":
        return response(409, {"message": "REVIEW 상태 모델만 테스트 이미지를 업로드할 수 있습니다."})

    # 테스트 이미지는 모델 artifact와 분리된 prefix에 저장
    filename = slug(payload.get("filename") or "test-image.jpg")
    content_type = payload.get("contentType") or "image/jpeg"
    timestamp = int(datetime.now(timezone.utc).timestamp())
    image_key = f"test-images/{model_id}/{timestamp}-{filename}"

    # 프론트엔드가 테스트 이미지를 S3에 직접 PUT할 수 있는 URL 생성
    upload_url = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": MODEL_BUCKET,
            "Key": image_key,
            "ContentType": content_type,
        },
        ExpiresIn=900,
    )

    return response(201, {"uploadUrl": upload_url, "imageKey": image_key})


def approve_model(event: dict[str, Any]) -> dict[str, Any]:
    """테스트 추론 결과가 있는 REVIEW 모델을 PRODUCTION 상태로 변경한다."""

    # 승인할 모델이 테스트 완료 상태인지 확인
    model_id = event["pathParameters"]["modelId"]
    item = table.get_item(Key={"modelId": model_id}).get("Item")
    if not item:
        return response(404, {"message": "모델을 찾을 수 없습니다."})
    if item["status"] != "REVIEW":
        return response(409, {"message": "REVIEW 상태 모델만 승인할 수 있습니다."})
    if "lastTestResult" not in item:
        return response(409, {"message": "테스트 추론을 먼저 실행해야 합니다."})

    # 승인 상태와 수정 시각 갱신
    updated_at = now_iso()
    table.update_item(
        Key={"modelId": model_id},
        UpdateExpression="SET #status = :production, updatedAt = :updated_at",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":production": "PRODUCTION",
            ":updated_at": updated_at,
        },
    )

    # Uploader가 구독한 SNS Topic으로 승인 알림 발송
    sns_client.publish(
        TopicArn=APPROVAL_TOPIC_ARN,
        Subject="[모델 배포 알림] Production 승인",
        Message=(
            f"{model_id} 모델이 Production 모델로 승인되었습니다.\n\n"
            f"Accuracy: {to_jsonable(item['accuracy'])}\n"
            f"S3: {item['artifactKey']}\n"
            f"Last test: {json.dumps(to_jsonable(item['lastTestResult']), ensure_ascii=False)}"
        ),
    )

    return response(200, {"modelId": model_id, "status": "PRODUCTION"})


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """HTTP method와 path에 맞는 API 핸들러로 요청을 라우팅한다."""

    method = event.get("requestContext", {}).get("http", {}).get("method")
    path = event.get("rawPath") or event.get("path") or ""

    # CORS preflight 요청 처리
    if method == "OPTIONS":
        return response(200, {"ok": True})

    try:
        if method == "POST" and path.endswith("/models/upload-url"):
            return create_upload_url(event)
        if method == "GET" and path.endswith("/models"):
            return list_models()
        if method == "POST" and path.endswith("/test-image-url"):
            return create_test_image_url(event)
        if method == "POST" and path.endswith("/test-inference"):
            return run_test_inference(event)
        if method == "PATCH" and path.endswith("/status"):
            return approve_model(event)
        return response(404, {"message": "지원하지 않는 API 경로입니다."})
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return response(409, {"message": "이미 같은 modelId가 등록되어 있습니다."})
    except KeyError as error:
        return response(400, {"message": f"필수 입력값이 없습니다: {error}"})
