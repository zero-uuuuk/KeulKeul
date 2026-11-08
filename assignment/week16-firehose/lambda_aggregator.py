"""
집계 Lambda — Athena 조회 결과를 data.json 하나로 만들어 웹 버킷에 올린다.
EventBridge Scheduler가 1분마다 호출. 정적 대시보드(index.html)가 이 파일을 읽는다.

환경 변수
  ATHENA_DB        week16_firehose_db
  ATHENA_TABLE     bike_status
  ATHENA_OUTPUT    s3://keulkeul-week16-{ACCOUNT_ID}-{성}/athena-results/
  WEB_BUCKET       keulkeul-week16-{ACCOUNT_ID}-{성}-web
  DATA_BUCKET      keulkeul-week16-{ACCOUNT_ID}-{성}        (파티션 등록용 LOCATION)
  FOCUS_STATIONS   ST-2327                                   (쉼표로 여러 개 가능)

Lambda 설정
  Runtime  Python 3.12
  Timeout  1 min
  권한     AmazonAthenaFullAccess, AmazonS3FullAccess (실습용)

하는 일
  1. 현재 시각·직전 시각의 hour 파티션을 Athena에 등록 (ALTER TABLE ADD IF NOT EXISTS)
  2. 쿼리 3개: 최근 2회 폴링 전체 / 3시간 추이 / 관심 대여소 3시간 시계열
  3. 대시보드가 바로 그릴 수 있는 형태로 가공해 data.json 업로드
"""

import csv
import io
import json
import os
import time
from datetime import datetime, timezone, timedelta

import boto3

KST = timezone(timedelta(hours=9))
FULL_POLL = 2000

athena = boto3.client("athena")
s3 = boto3.client("s3")

DB = os.environ.get("ATHENA_DB", "week16_firehose_db")
TABLE = os.environ.get("ATHENA_TABLE", "bike_status")
OUTPUT = os.environ["ATHENA_OUTPUT"]
WEB_BUCKET = os.environ["WEB_BUCKET"]
DATA_BUCKET = os.environ["DATA_BUCKET"]
FOCUS = [x.strip() for x in os.environ.get("FOCUS_STATIONS", "ST-2327").split(",") if x.strip()]
T = f"{DB}.{TABLE}"


# ----------------------------------------------------------------- Athena
def run(sql: str, want_rows: bool = True) -> list[dict]:
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DB},
        ResultConfiguration={"OutputLocation": OUTPUT},
    )["QueryExecutionId"]
    while True:
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.4)
    if st["State"] != "SUCCEEDED":
        raise RuntimeError(st.get("StateChangeReason", st["State"]))
    if not want_rows:
        return []
    bucket, key = OUTPUT.replace("s3://", "").split("/", 1)
    body = s3.get_object(Bucket=bucket, Key=f"{key}{qid}.csv")["Body"].read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(body)))


def hours(n: int) -> list[str]:
    now = datetime.now(KST)
    return [(now - timedelta(hours=i)).strftime("%H") for i in range(n)]


def hours_clause(n: int) -> str:
    return ", ".join(f"'{h}'" for h in hours(n))


def register_partitions():
    """현재·직전 시간 폴더를 파티션으로 등록. 이미 있으면 무시."""
    parts = " ".join(
        f"PARTITION (hour='{h}') LOCATION 's3://{DATA_BUCKET}/clean/hour={h}/'" for h in hours(2)
    )
    run(f"ALTER TABLE {T} ADD IF NOT EXISTS {parts}", want_rows=False)


# ----------------------------------------------------------------- 쿼리
def q_two_polls() -> list[dict]:
    return run(f"""
    WITH counts AS (
      SELECT polled_at, COUNT(*) AS c FROM {T}
      WHERE hour IN ({hours_clause(2)}) GROUP BY polled_at
    ),
    picked AS (
      SELECT polled_at FROM counts WHERE c >= {FULL_POLL} ORDER BY polled_at DESC LIMIT 2
    )
    SELECT stationId, stationName, rackTotCnt, parkingBikeTotCnt, empty_racks,
           is_empty, is_overflow, stationLatitude AS lat, stationLongitude AS lon, polled_at
    FROM {T}
    WHERE hour IN ({hours_clause(2)}) AND polled_at IN (SELECT polled_at FROM picked)
    """)


def q_trend() -> list[dict]:
    return run(f"""
    SELECT polled_at,
           SUM(parkingBikeTotCnt) AS total_bikes,
           SUM(CASE WHEN is_empty THEN 1 ELSE 0 END) AS empty_cnt,
           COUNT(*) AS records
    FROM {T}
    WHERE hour IN ({hours_clause(3)})
    GROUP BY polled_at HAVING COUNT(*) >= {FULL_POLL}
    ORDER BY polled_at
    """)


def q_series() -> list[dict]:
    ids = ", ".join(f"'{i}'" for i in FOCUS)
    return run(f"""
    SELECT stationId, polled_at, parkingBikeTotCnt
    FROM {T}
    WHERE stationId IN ({ids}) AND hour IN ({hours_clause(3)})
    ORDER BY polled_at
    """)


# ----------------------------------------------------------------- 가공
def to_bool(v) -> bool:
    return str(v).lower() == "true"


def num(v, cast=int, default=0):
    """Athena는 NULL을 빈 문자열로 돌려준다. 빈 값은 default로."""
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


def build(two: list[dict], trend: list[dict], series: list[dict]) -> dict:
    times = sorted({r["polled_at"] for r in two}, reverse=True)
    if not times:
        return {"generated_at": datetime.now(KST).isoformat(timespec="seconds"), "empty": True}
    two = [r for r in two if r.get("stationId") and r.get("parkingBikeTotCnt") not in ("", None)]
    latest = [r for r in two if r["polled_at"] == times[0]]
    prev = {r["stationId"]: num(r["parkingBikeTotCnt"]) for r in two if len(times) > 1 and r["polled_at"] == times[1]}

    stations, feed = [], []
    bikes = empty = over = rentals = returns = changed = 0
    for r in latest:
        b = num(r["parkingBikeTotCnt"])
        d = b - prev[r["stationId"]] if r["stationId"] in prev else None
        if d:
            changed += 1
            if d < 0: rentals += -d
            else: returns += d
            feed.append({"name": r["stationName"], "prev": prev[r["stationId"]], "now": b, "delta": d})
        ie, io_ = to_bool(r["is_empty"]), to_bool(r["is_overflow"])
        bikes += b; empty += ie; over += io_
        stations.append({
            "id": r["stationId"], "name": r["stationName"],
            "lat": num(r["lat"], float, 0.0), "lon": num(r["lon"], float, 0.0),
            "bikes": b, "racks": num(r["rackTotCnt"]), "empty_racks": num(r["empty_racks"]),
            "is_empty": ie, "is_overflow": io_, "delta": d,
        })
    feed.sort(key=lambda x: -abs(x["delta"]))

    prev_bikes = sum(prev.values()) if prev else None
    prev_rows = [r for r in two if len(times) > 1 and r["polled_at"] == times[1]]
    prev_empty = sum(to_bool(r["is_empty"]) for r in prev_rows) if prev_rows else None
    prev_over = sum(to_bool(r["is_overflow"]) for r in prev_rows) if prev_rows else None

    ser = {}
    for r in series:
        ser.setdefault(r["stationId"], []).append([r["polled_at"], num(r["parkingBikeTotCnt"])])
    by_id = {s["id"]: s for s in stations}
    focus = [{**by_id[i], "series": ser.get(i, [])} for i in FOCUS if i in by_id]

    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "polled_at": times[0],
        "prev_polled_at": times[1] if len(times) > 1 else None,
        "totals": {"stations": len(latest), "bikes": bikes, "empty": empty, "overflow": over,
                   "records_3h": sum(num(t["records"]) for t in trend)},
        "deltas": {"bikes": bikes - prev_bikes if prev_bikes is not None else None,
                   "empty": empty - prev_empty if prev_empty is not None else None,
                   "overflow": over - prev_over if prev_over is not None else None},
        "changes": {"rentals": rentals, "returns": returns, "changed": changed},
        "feed": feed[:10],
        "trend": [{"t": t["polled_at"], "bikes": num(t["total_bikes"]), "empty": num(t["empty_cnt"])} for t in trend],
        "focus": focus,
        "stations": stations,
    }


# ----------------------------------------------------------------- 핸들러
def lambda_handler(event, context):
    register_partitions()
    data = build(q_two_polls(), q_trend(), q_series())
    s3.put_object(
        Bucket=WEB_BUCKET, Key="data.json",
        Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="no-cache, max-age=0",
    )
    print(f"data.json uploaded: stations={data.get('totals', {}).get('stations')} polled_at={data.get('polled_at')}")
    return {"statusCode": 200, "polled_at": data.get("polled_at")}
