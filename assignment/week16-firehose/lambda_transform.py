"""
Amazon Data Firehose 변환용 Lambda (Python 3.12)

하는 일
  1. API가 문자열로 준 숫자를 int / double로 변환
  2. 파생 필드 추가: empty_racks, is_empty, is_overflow, station_no
  3. Dynamic Partitioning 키(hour) 를 metadata.partitionKeys 로 전달
  4. 깨진 레코드는 ProcessingFailed 로 표시 → Firehose가 error/ 폴더로 보냄

Firehose 콘솔 설정
  - Transform source records with AWS Lambda: 이 함수 선택
  - Buffer size 1MB / interval 60s (Lambda 호출 단위)
  - Dynamic partitioning: Enabled, Inline parsing 대신 Lambda 키 사용
      partition key = hour,  S3 prefix = clean/hour=!{partitionKeyFromLambda:hour}/
      error prefix  = error/!{firehose:error-output-type}/
"""

import base64
import json
import re

STATION_NO_RE = re.compile(r"^\s*(\d+)\s*\.")

REQUIRED = ("stationId", "stationName", "rackTotCnt", "parkingBikeTotCnt",
            "shared", "stationLatitude", "stationLongitude", "polled_at")


def transform(raw: dict) -> dict:
    """원본 레코드 1건 → 정제 레코드 1건. 문제가 있으면 ValueError."""
    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        raise ValueError(f"missing fields: {missing}")

    rack = int(raw["rackTotCnt"])
    bikes = int(raw["parkingBikeTotCnt"])
    shared = int(raw["shared"])

    m = STATION_NO_RE.match(raw["stationName"])
    station_no = int(m.group(1)) if m else None

    # polled_at 예: 2026-11-04T13:36:12+09:00  → hour = "13"
    hour = raw["polled_at"][11:13]
    if not hour.isdigit():
        raise ValueError(f"bad polled_at: {raw['polled_at']}")

    return {
        # ---- 원본 (이름 유지, 타입만 변환)
        "stationId": raw["stationId"],
        "stationName": raw["stationName"],
        "rackTotCnt": rack,
        "parkingBikeTotCnt": bikes,
        "shared": shared,
        "stationLatitude": float(raw["stationLatitude"]),
        "stationLongitude": float(raw["stationLongitude"]),
        "polled_at": raw["polled_at"],
        # ---- 파생
        "station_no": station_no,
        "empty_racks": max(rack - bikes, 0),
        "is_empty": bikes == 0,
        "is_overflow": bikes > rack,
        "hour": hour,
    }


def lambda_handler(event, context):
    output = []
    for rec in event["records"]:
        raw_bytes = base64.b64decode(rec["data"])
        try:
            raw = json.loads(raw_bytes.decode("utf-8"))
            clean = transform(raw)
            data = (json.dumps(clean, ensure_ascii=False) + "\n").encode("utf-8")
            output.append({
                "recordId": rec["recordId"],
                "result": "Ok",
                "data": base64.b64encode(data).decode("ascii"),
                "metadata": {"partitionKeys": {"hour": clean["hour"]}},
            })
        except Exception as e:  # JSON 파싱 실패, 타입 변환 실패, 필드 누락 등
            print(f"ProcessingFailed recordId={rec['recordId']} reason={e!r}")
            output.append({
                "recordId": rec["recordId"],
                "result": "ProcessingFailed",
                "data": rec["data"],     # 원본 그대로 돌려주면 error/ 폴더에 보존됨
            })
    return {"records": output}
