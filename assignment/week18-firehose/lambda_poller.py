"""
따릉이 실시간 대여정보 → Firehose 폴러 (Lambda 버전)

EventBridge Scheduler가 1분마다 이 함수를 호출하고, 함수 안에서 CALLS_PER_RUN번
(기본 2번, 30초 간격) API를 호출해 Firehose로 보낸다. → 결과적으로 30초 폴링.

환경 변수
  SEOUL_API_KEY     서울열린데이터광장 인증키 (필수)
  FIREHOSE_STREAM   Firehose 스트림 이름 (필수)
  CALLS_PER_RUN     한 번 실행에 API를 호출하는 횟수 (기본 2)
  GAP_SECONDS       호출 사이 대기 초 (기본 30)
  CORRUPT_PER_RUN   매 폴링마다 일부러 깨뜨릴 레코드 수 (기본 0, Assignment 2 시연용 5)

Lambda 설정
  Runtime  Python 3.12
  Timeout  1 min 30 sec  (2회 호출 + 30초 대기 + 전송 여유)
  권한     firehose:PutRecordBatch

주의: 서울 API는 키당 하루 호출 한도(기본 1,000회)가 있다. 1분 주기 × 2회 × 3페이지면
      하루 8,640회라 상시 운영은 불가. 발표 당일만 1분 주기, 평소엔 5분 주기로 둔다.
"""

import json
import os
import random
import time
import urllib.request
from datetime import datetime, timezone, timedelta

import boto3

KST = timezone(timedelta(hours=9))
API_BASE = "http://openapi.seoul.go.kr:8088/{key}/json/bikeList/{start}/{end}/"
PAGE_SIZE = 1000
BATCH_SIZE = 500

firehose = boto3.client("firehose")


def fetch_snapshot(key: str) -> list[dict]:
    rows, start = [], 1
    while True:
        url = API_BASE.format(key=key, start=start, end=start + PAGE_SIZE - 1)
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        status = body.get("rentBikeStatus")
        if status is None:
            result = body.get("RESULT", {})
            raise RuntimeError(f"API 오류: {result.get('CODE')} {result.get('MESSAGE')}")
        page = status.get("row", [])
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows


def send(stream: str, records: list[dict]) -> tuple[int, int]:
    ok = fail = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i : i + BATCH_SIZE]
        resp = firehose.put_record_batch(
            DeliveryStreamName=stream,
            Records=[{"Data": (json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8")} for r in chunk],
        )
        failed = resp.get("FailedPutCount", 0)
        if failed:
            retry = [chunk[j] for j, r in enumerate(resp["RequestResponses"]) if "ErrorCode" in r]
            resp2 = firehose.put_record_batch(
                DeliveryStreamName=stream,
                Records=[{"Data": (json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8")} for r in retry],
            )
            failed = resp2.get("FailedPutCount", 0)
        ok += len(chunk) - failed
        fail += failed
    return ok, fail


def corrupt(records: list[dict], n: int) -> list[dict]:
    """Assignment 2 시연용: n개 레코드를 일부러 망가뜨린다."""
    out = list(records)
    for i in random.sample(range(len(out)), min(n, len(out))):
        r = dict(out[i])
        if random.random() < 0.5:
            r["parkingBikeTotCnt"] = "N/A"
        else:
            r.pop("stationId", None)
        out[i] = r
    return out


def poll_once(key: str, stream: str, n_corrupt: int = 0) -> dict:
    polled_at = datetime.now(KST).isoformat(timespec="seconds")
    rows = fetch_snapshot(key)
    records = [{**row, "polled_at": polled_at} for row in rows]
    if n_corrupt:
        records = corrupt(records, n_corrupt)
    ok, fail = send(stream, records)
    print(f"polled_at={polled_at} sent={ok} failed={fail}")
    return {"polled_at": polled_at, "sent": ok, "failed": fail}


def lambda_handler(event, context):
    key = os.environ["SEOUL_API_KEY"]
    stream = os.environ["FIREHOSE_STREAM"]
    calls = int(os.environ.get("CALLS_PER_RUN", "2"))
    gap = int(os.environ.get("GAP_SECONDS", "30"))
    n_corrupt = int(os.environ.get("CORRUPT_PER_RUN", "0"))

    results = []
    for i in range(calls):
        t0 = time.time()
        results.append(poll_once(key, stream, n_corrupt))
        if i < calls - 1:
            time.sleep(max(0.0, gap - (time.time() - t0)))
    return {"statusCode": 200, "body": json.dumps(results, ensure_ascii=False)}
