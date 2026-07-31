"""역할: Agent Lambda가 호출하는 대화 history 검색 tool을 처리한다.

상세 내용:
  1. Agent Lambda가 전달한 sessionId, keyword 값을 검증한다.
  2. DynamoDB messages table에서 같은 sessionId의 최근 메시지를 조회한다.
  3. keyword가 포함된 메시지만 골라 OpenAI function tool 결과로 반환한다.
"""

from typing import Any

import boto3
from boto3.dynamodb.conditions import Key


# ---------------------------------------------------------------------------
# AWS 리소스
# ---------------------------------------------------------------------------
messages_table = boto3.resource("dynamodb").Table("keulkeul-agent-messages")


# ---------------------------------------------------------------------------
# Lambda 진입점
# ---------------------------------------------------------------------------
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """현재 session의 대화 history에서 keyword가 포함된 메시지를 검색한다."""

    # 필수 입력값을 확인하고 검색 범위를 제한
    session_id = event.get("sessionId")
    keyword = (event.get("keyword") or "").strip()
    if not session_id or not keyword:
        return {"ok": False, "message": "sessionId와 keyword가 필요합니다.", "items": []}

    # 최근 메시지부터 가져온 뒤 Lambda 안에서 단순 keyword 포함 여부를 검사
    result = messages_table.query(
        KeyConditionExpression=Key("sessionId").eq(session_id),
        ScanIndexForward=False,
        Limit=50,
    )
    
    # 조회 결과 formatting
    matched_items = [
        {
            "role": item.get("role", ""),
            "content": item.get("content", ""),
            "createdAt": item.get("createdAt", ""),
        }
        for item in result.get("Items", [])
        if keyword.lower() in (item.get("content") or "").lower()
    ][:5] # 최대 5개

    return {
        "ok": True,
        "items": matched_items,
    }
