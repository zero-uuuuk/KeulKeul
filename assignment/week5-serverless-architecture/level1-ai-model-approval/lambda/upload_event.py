"""역할: S3 ONNX 모델 업로드 이벤트를 받아 모델 상태를 REVIEW로 변경한다.

상세 과정:
  1. S3 ObjectCreated 이벤트에서 object key를 읽는다.
  2. models/{modelName}/{version}/{filename} 구조에서 modelId를 복원한다.
  3. DynamoDB item이 PENDING_UPLOAD일 때만 REVIEW로 변경한다.
  4. 상태 변경에 성공한 경우에만 SNS 검토 알림을 발행한다.
"""

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote_plus

import boto3


# ---------------------------------------------------------------------------
# AWS 클라이언트 및 환경 변수
# ---------------------------------------------------------------------------
TABLE_NAME = os.environ["TABLE_NAME"]
REVIEW_TOPIC_ARN = os.environ["REVIEW_TOPIC_ARN"]

table = boto3.resource("dynamodb").Table(TABLE_NAME)
sns_client = boto3.client("sns")


# ---------------------------------------------------------------------------
# Lambda 진입점
# ---------------------------------------------------------------------------
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """S3 업로드 이벤트를 처리하고 중복 이벤트는 정상 종료한다."""

    for record in event.get("Records", []):
        # 업로드된 S3 key에서 modelId 복원
        object_key = unquote_plus(record["s3"]["object"]["key"])
        parts = object_key.split("/")
        if len(parts) < 4:
            continue
        model_id = f"{parts[1]}-{parts[2]}"

        # PENDING_UPLOAD 상태일 때만 REVIEW로 변경
        try:
            table.update_item(
                Key={"modelId": model_id},
                ConditionExpression="attribute_exists(modelId) AND artifactKey = :key AND #status = :pending",
                UpdateExpression="SET #status = :review, updatedAt = :updated_at",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":key": object_key,
                    ":pending": "PENDING_UPLOAD",
                    ":review": "REVIEW",
                    ":updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            continue

        # 상태 변경에 성공한 경우에만 검토 알림 발송
        sns_client.publish(
            TopicArn=REVIEW_TOPIC_ARN,
            Subject="[모델 검토 알림] 새 후보 등록",
            Message=(
                "새로운 모델 후보가 등록되었습니다.\n\n"
                f"Model: {model_id}\n"
                "Status: REVIEW\n"
                f"S3: {object_key}"
            ),
        )

    return {"ok": True}
