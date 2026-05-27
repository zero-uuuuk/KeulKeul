"""역할: ALB 뒤의 Auto Scaling 서버에 단계별 HTTP 부하를 발생시킨다.

상세 과정:
  1. 워밍업, 폭증, 정상 복귀, 관찰 단계별로 요청 강도를 다르게 적용한다.
  2. 각 단계에서 응답 시간, 성공 수, 실패 수, p95 응답 시간을 주기적으로 출력한다.
  3. 요청 실패나 타임아웃은 집계에 포함하되 전체 부하 테스트는 계속 진행한다.
"""

from __future__ import annotations

import argparse
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus


# ---------------------------------------------------------------------------
# 기본 부하 테스트 설정
# ---------------------------------------------------------------------------

DEFAULT_REQUEST_TIMEOUT_SECONDS = 5
DEFAULT_REPORT_INTERVAL_SECONDS = 10
DEFAULT_WORK_MS = 300


@dataclass(frozen=True)
class LoadPhase:
    """부하 테스트의 한 구간에 필요한 실행 설정을 표현한다."""

    name: str
    duration_seconds: int
    concurrency: int
    work_ms: int


@dataclass
class MetricsSnapshot:
    """특정 집계 구간의 요청 처리 결과를 표현한다."""

    success_count: int
    failure_count: int
    response_times_ms: list[float]


# ---------------------------------------------------------------------------
# 요청 결과 집계
# ---------------------------------------------------------------------------

class MetricsCollector:
    """여러 worker thread의 요청 결과를 thread-safe하게 모은다."""

    def __init__(self) -> None:
        """공유 집계 상태와 동시성 제어용 lock을 초기화한다."""

        # 성공과 실패는 분리해서 집계하고, 응답 시간은 성공 요청 기준으로 계산한다.
        self._success_count = 0
        self._failure_count = 0
        self._response_times_ms: list[float] = []
        self._lock = threading.Lock()

    def record_success(self, response_time_ms: float) -> None:
        """성공한 요청의 응답 시간을 집계한다."""

        # 여러 worker가 동시에 기록하므로 lock 안에서만 공유 상태를 갱신한다.
        with self._lock:
            self._success_count += 1
            self._response_times_ms.append(response_time_ms)

    def record_failure(self) -> None:
        """실패한 요청 수를 집계한다."""

        # 실패 원인은 출력량을 줄이기 위해 개별 로그 대신 총합으로만 관리한다.
        with self._lock:
            self._failure_count += 1

    def drain(self) -> MetricsSnapshot:
        """현재까지의 집계 값을 반환하고 다음 출력 구간을 위해 초기화한다."""

        # 보고 주기마다 값을 비워 구간별 RPS와 에러율을 계산할 수 있게 한다.
        with self._lock:
            snapshot = MetricsSnapshot(
                success_count=self._success_count,
                failure_count=self._failure_count,
                response_times_ms=self._response_times_ms,
            )
            self._success_count = 0
            self._failure_count = 0
            self._response_times_ms = []

        return snapshot


# ---------------------------------------------------------------------------
# HTTP 요청 실행
# ---------------------------------------------------------------------------

def build_request_url(host: str, work_ms: int) -> str:
    """ALB host와 CPU 작업 시간을 조합해 요청 URL을 만든다."""

    # 사용자가 host 끝에 /를 붙여도 항상 루트 경로에 query string이 붙도록 정규화한다.
    normalized_host = host.rstrip("/")
    query_string = urllib.parse.urlencode({"work_ms": work_ms})
    return f"{normalized_host}/?{query_string}"


def send_request(url: str, timeout_seconds: int) -> float | None:
    """HTTP GET 요청을 보내고 성공하면 응답 시간을 ms 단위로 반환한다."""

    # ALB와 target instance의 일시적인 오류는 예외로 처리해 부하 테스트를 계속 진행한다.
    started_at = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            response.read()
            if response.status != HTTPStatus.OK:
                return None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    return (time.perf_counter() - started_at) * 1_000


def run_worker(
    url: str,
    timeout_seconds: int,
    stop_event: threading.Event,
    metrics: MetricsCollector,
) -> None:
    """stop_event가 설정될 때까지 같은 URL로 HTTP 요청을 반복한다."""

    # 각 worker는 독립적으로 요청을 반복하고, 결과만 공유 collector에 기록한다.
    while not stop_event.is_set():
        response_time_ms = send_request(url, timeout_seconds)
        if response_time_ms is None:
            metrics.record_failure()
            continue

        metrics.record_success(response_time_ms)


# ---------------------------------------------------------------------------
# 출력 및 통계 계산
# ---------------------------------------------------------------------------

def calculate_p95(response_times_ms: list[float]) -> float:
    """응답 시간 목록에서 p95 값을 계산한다."""

    # 표본이 적은 구간에서는 최댓값을 p95로 사용해 통계 함수의 예외를 피한다.
    if not response_times_ms:
        return 0.0
    if len(response_times_ms) < 20:
        return max(response_times_ms)

    return statistics.quantiles(response_times_ms, n=20)[18]


def print_report(phase_name: str, elapsed_seconds: int, interval_seconds: int, snapshot: MetricsSnapshot) -> None:
    """한 보고 구간의 요청 처리 결과를 터미널에 출력한다."""

    # 성공/실패 합계를 기준으로 RPS와 에러율을 계산한다.
    total_count = snapshot.success_count + snapshot.failure_count
    rps = total_count / max(interval_seconds, 1)
    error_rate = (snapshot.failure_count / total_count * 100) if total_count else 0.0

    # 성공 요청이 있는 경우에만 평균과 p95 응답 시간을 계산한다.
    if snapshot.response_times_ms:
        average_ms = statistics.mean(snapshot.response_times_ms)
        p95_ms = calculate_p95(snapshot.response_times_ms)
    else:
        average_ms = 0.0
        p95_ms = 0.0

    print(
        f"[{phase_name}] elapsed={elapsed_seconds:>4}s "
        f"rps={rps:>6.1f} success={snapshot.success_count:>5} "
        f"failure={snapshot.failure_count:>4} error={error_rate:>5.1f}% "
        f"avg={average_ms:>7.1f}ms p95={p95_ms:>7.1f}ms",
        flush=True,
    )


def print_phase_start(phase: LoadPhase, url: str) -> None:
    """새 부하 테스트 구간의 시작 정보를 출력한다."""

    # 현재 구간의 duration, concurrency, work_ms를 함께 보여 재현성을 높인다.
    print()
    print(f"== {phase.name} 시작 ==")
    print(
        f"duration={phase.duration_seconds}s, "
        f"concurrency={phase.concurrency}, work_ms={phase.work_ms}"
    )
    if phase.concurrency > 0:
        print(f"target={url}")


# ---------------------------------------------------------------------------
# 단계별 부하 실행
# ---------------------------------------------------------------------------

def run_observation_phase(phase: LoadPhase, report_interval_seconds: int) -> None:
    """요청을 보내지 않고 scale-in 여부를 관찰할 시간을 확보한다."""

    # 관찰 구간은 CPU 부하를 낮추기 위해 요청을 보내지 않고 경과 시간만 출력한다.
    print_phase_start(phase, url="")
    started_at = time.monotonic()
    while True:
        elapsed_seconds = int(time.monotonic() - started_at)
        if elapsed_seconds >= phase.duration_seconds:
            break

        sleep_seconds = min(report_interval_seconds, phase.duration_seconds - elapsed_seconds)
        time.sleep(sleep_seconds)
        elapsed_seconds = int(time.monotonic() - started_at)
        print(f"[{phase.name}] elapsed={elapsed_seconds:>4}s 요청 없이 관찰 중", flush=True)


def run_load_phase(
    host: str,
    phase: LoadPhase,
    timeout_seconds: int,
    report_interval_seconds: int,
) -> None:
    """지정된 동시성으로 한 부하 테스트 구간을 실행한다."""

    # concurrency가 0이면 요청 없이 관찰만 수행한다.
    if phase.concurrency <= 0:
        run_observation_phase(phase, report_interval_seconds)
        return

    # 단계별 work_ms가 포함된 URL을 만들고 worker thread를 시작한다.
    url = build_request_url(host, phase.work_ms)
    print_phase_start(phase, url)
    metrics = MetricsCollector()
    stop_event = threading.Event()
    workers = [
        threading.Thread(
            target=run_worker,
            args=(url, timeout_seconds, stop_event, metrics),
            daemon=True,
        )
        for _ in range(phase.concurrency)
    ]

    for worker in workers:
        worker.start()

    # 보고 주기마다 집계를 비우며 실시간 응답 시간과 에러율을 출력한다.
    started_at = time.monotonic()
    while True:
        elapsed_seconds = int(time.monotonic() - started_at)
        if elapsed_seconds >= phase.duration_seconds:
            break

        sleep_seconds = min(report_interval_seconds, phase.duration_seconds - elapsed_seconds)
        time.sleep(sleep_seconds)
        elapsed_seconds = int(time.monotonic() - started_at)
        snapshot = metrics.drain()
        print_report(phase.name, elapsed_seconds, sleep_seconds, snapshot)

    # worker 종료를 요청하고 짧게 join하여 다음 단계와 출력이 섞이지 않게 한다.
    stop_event.set()
    for worker in workers:
        worker.join(timeout=timeout_seconds + 1)


# ---------------------------------------------------------------------------
# 명령행 인터페이스
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """부하 테스트 실행에 필요한 명령행 인자를 파싱한다."""

    # 과제 문서의 기본 실행 형태는 --host만 넘겨도 동작하도록 구성한다.
    parser = argparse.ArgumentParser(description="ALB 대상 Auto Scaling 부하 테스트")
    parser.add_argument("--host", required=True, help="예: http://my-alb.ap-northeast-2.elb.amazonaws.com")
    parser.add_argument("--work-ms", type=int, default=DEFAULT_WORK_MS, help="폭증 구간 요청별 CPU 작업 시간(ms)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_REQUEST_TIMEOUT_SECONDS, help="요청 타임아웃(초)")
    parser.add_argument(
        "--report-interval",
        type=int,
        default=DEFAULT_REPORT_INTERVAL_SECONDS,
        help="진행 상황 출력 주기(초)",
    )
    return parser.parse_args()


def build_phases(work_ms: int) -> list[LoadPhase]:
    """과제 시나리오에 맞는 부하 테스트 단계를 생성한다."""

    # 폭증 구간은 t3.micro 기준 CPU 상승을 관찰하기 쉽도록 기본 work_ms를 크게 적용한다.
    return [
        LoadPhase(name="워밍업", duration_seconds=180, concurrency=5, work_ms=120),
        LoadPhase(name="폭증", duration_seconds=360, concurrency=80, work_ms=work_ms),
        LoadPhase(name="정상 복귀", duration_seconds=180, concurrency=5, work_ms=120),
        LoadPhase(name="scale-in 관찰", duration_seconds=900, concurrency=0, work_ms=0),
    ]


def main() -> None:
    """명령행 인자를 기반으로 전체 부하 테스트 시나리오를 실행한다."""

    # 각 단계를 순서대로 실행하여 CloudWatch에서 scale-out과 scale-in 흐름을 관찰한다.
    args = parse_args()
    for phase in build_phases(args.work_ms):
        run_load_phase(
            host=args.host,
            phase=phase,
            timeout_seconds=args.timeout,
            report_interval_seconds=args.report_interval,
        )

    print()
    print("부하 테스트가 완료되었습니다. CloudWatch 지표와 ASG 이벤트를 확인하세요.")


if __name__ == "__main__":
    main()
