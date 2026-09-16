"""원격 웹 서버에 무작위 시청 요청을 대량으로 보내 실제 로그를 쌓는다."""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


# ---------------------------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------------------------

DEFAULT_COUNT = 10_000
DEFAULT_CONCURRENCY = 20
REQUEST_TIMEOUT_SECONDS = 10
PROGRESS_INTERVAL_SECONDS = 2.0

VIEWER_ID_MAX = 2_500
WATCH_MINUTES_RANGE = (5, 120)


# ---------------------------------------------------------------------------
# 요청 생성 및 전송
# ---------------------------------------------------------------------------

def fetch_catalog(base_url: str) -> tuple[list[dict], list[int], list[str]]:
    """서버에서 작품 목록과 기기 목록을 받아 작품·가중치·기기로 나눠 반환한다."""

    with urllib.request.urlopen(f"{base_url}/api/catalog", timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.load(response)

    catalog = payload["catalog"]
    # 가중치를 두면 작품별 시청 수가 고르지 않게 쌓여 Athena 집계와 AI 리포트에 의미가 생긴다.
    weights = [work.get("weight", 1) for work in catalog]
    return catalog, weights, payload["devices"]


def build_payload(catalog: list[dict], weights: list[int], devices: list[str]) -> bytes:
    """시청 요청 한 건의 본문을 무작위로 만든다."""

    work = random.choices(catalog, weights=weights, k=1)[0]
    body = {
        "viewer_id": f"viewer-{random.randint(1, VIEWER_ID_MAX):04d}",
        "title": work["title"],
        "device": random.choice(devices),
        "watch_minutes": random.randint(*WATCH_MINUTES_RANGE),
        "source": "traffic",
    }
    return json.dumps(body).encode("utf-8")


def send_watch(url: str, payload: bytes) -> str | None:
    """시청 요청 한 건을 보낸다. 성공하면 None을, 실패하면 실패 사유를 반환한다."""

    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            response.read()
        return None
    except urllib.error.HTTPError as error:
        return f"HTTP {error.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        # 연결 거부나 Timeout은 서버 기동 상태나 Security Group 설정을 되짚어 보게 하는 신호다.
        return f"{type(error).__name__}: {error}"


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def run_traffic(base_url: str, count: int, concurrency: int) -> int:
    """요청을 count건 보내고 결과를 요약 출력한 뒤 실패 수를 반환한다."""

    catalog, weights, devices = fetch_catalog(base_url)
    print(f"작품 {len(catalog)}종 / 기기 {len(devices)}종 확인. {count:,}건 전송 시작 (동시성 {concurrency})", flush=True)

    watch_url = f"{base_url}/api/watch"
    failures: collections.Counter[str] = collections.Counter()
    completed = 0
    lock = threading.Lock()
    started_at = time.monotonic()
    last_report = started_at

    def worker(_: int) -> None:
        nonlocal completed, last_report
        reason = send_watch(watch_url, build_payload(catalog, weights, devices))
        with lock:
            completed += 1
            if reason is not None:
                failures[reason] += 1
            now = time.monotonic()
            if now - last_report >= PROGRESS_INTERVAL_SECONDS:
                last_report = now
                rate = completed / (now - started_at)
                print(f"  {completed:,}/{count:,} 완료 · 실패 {sum(failures.values()):,} · {rate:,.0f} req/s", flush=True)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(worker, range(count)))

    elapsed = time.monotonic() - started_at
    failure_count = sum(failures.values())
    print(f"\n완료: 성공 {count - failure_count:,}건 / 실패 {failure_count:,}건 / {elapsed:,.1f}초", flush=True)
    for reason, number in failures.most_common(5):
        print(f"  실패 사유 {reason}: {number:,}건", flush=True)
    if failure_count:
        print("실패한 요청이 있다. 분석을 시작하기 전에 다시 실행한다.", flush=True)
    return failure_count


def main() -> None:
    """실행 인자를 읽어 Traffic을 생성한다."""

    parser = argparse.ArgumentParser(description="Week10 시청 요청 생성 Script")
    parser.add_argument("--url", required=True, help="웹 서버 주소 (예: http://EC2_PUBLIC_IP:8000)")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="보낼 요청 수")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="동시 요청 수")
    args = parser.parse_args()

    sys.exit(1 if run_traffic(args.url.rstrip("/"), args.count, args.concurrency) else 0)


if __name__ == "__main__":
    main()
