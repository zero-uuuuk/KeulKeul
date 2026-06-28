"""역할: S3 객체 생성 이벤트를 받아 업로드된 객체 정보를 로그로 남긴다.

상세 과정:
  1. S3 Event Notification의 Records 배열에서 bucket, object key, size를 읽는다.
  2. URL 인코딩된 object key를 사람이 읽을 수 있는 파일명으로 복원한다.
  3. 처리한 객체 정보를 CloudWatch Logs와 Lambda 반환값으로 남긴다.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote_plus


# ---------------------------------------------------------------------------
# S3 이벤트 처리
# ---------------------------------------------------------------------------

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """S3 객체 생성 이벤트에서 업로드된 파일 정보를 추출해 반환한다."""

    # S3는 한 번의 Lambda 실행에 여러 객체 이벤트를 Records 배열로 전달할 수 있다.
    processed_records: list[dict[str, Any]] = []
    records = event.get("Records", [])

    # 각 S3 이벤트에서 버킷 이름, 객체 키, 객체 크기, 이벤트 이름을 추출한다.
    for record in records:
        s3_info = record.get("s3", {})
        bucket_info = s3_info.get("bucket", {})
        object_info = s3_info.get("object", {})

        # S3 object key는 URL 인코딩되어 오므로 공백과 한글 파일명을 복원한다.
        bucket_name = bucket_info.get("name", "")
        object_key = unquote_plus(object_info.get("key", ""))
        object_size = object_info.get("size", 0)
        event_name = record.get("eventName", "")
        request_id = getattr(context, "aws_request_id", "")

        # CloudWatch Logs에서 업로드 이벤트가 Lambda까지 도착했는지 확인할 수 있게 한다.
        print(
            f"S3 객체 이벤트: bucket={bucket_name}, key={object_key}, "
            f"size={object_size}, event={event_name}, request_id={request_id}"
        )

        # Lambda 테스트 결과 화면에서도 처리한 객체 목록을 확인할 수 있게 반환값을 만든다.
        processed_records.append(
            {
                "bucket": bucket_name,
                "key": object_key,
                "size": object_size,
                "event": event_name,
                "request_id": request_id,
            }
        )

    return {
        "processed_count": len(processed_records),
        "records": processed_records,
    }
