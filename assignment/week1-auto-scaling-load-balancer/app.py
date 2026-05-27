"""역할: Auto Scaling 실습용 HTTP 서버를 실행한다.

상세 과정:
  1. ALB 헬스 체크를 위한 /health 요청에는 CPU 부하 없이 200 OK를 반환한다.
  2. 일반 / 요청에는 지정된 시간만큼 CPU 연산을 수행한 뒤 호스트 정보를 반환한다.
  3. 잘못된 경로나 종료 신호는 명확한 HTTP 응답과 안전한 서버 종료로 처리한다.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


# ---------------------------------------------------------------------------
# 기본 설정 (포트 및 부하 강도)
# ---------------------------------------------------------------------------

DEFAULT_PORT = 80
DEFAULT_CPU_WORK_MS = 120
MAX_CPU_WORK_MS = 2_000


# ---------------------------------------------------------------------------
# CPU 부하 생성
# ---------------------------------------------------------------------------

def run_cpu_work(work_ms: int) -> dict[str, int | float]:
    """지정된 밀리초 동안 순수 Python 정수 연산을 반복해 CPU 사용률을 높인다."""

    # 과도한 부하 설정으로 인스턴스가 응답 불능 상태가 되지 않도록 상한을 둔다.
    bounded_work_ms = max(0, min(work_ms, MAX_CPU_WORK_MS))
    deadline = time.perf_counter() + (bounded_work_ms / 1_000)

    # 단순하지만 최적화로 제거되지 않는 정수 연산을 반복하여 CPU 시간을 사용한다.
    iteration_count = 0
    checksum = 0
    while time.perf_counter() < deadline:
        checksum = (checksum * 33 + iteration_count) % 1_000_000_007
        iteration_count += 1

    # 실제 사용된 시간과 반복 횟수를 응답에 포함해 부하 강도 확인을 쉽게 한다.
    return {
        "requested_cpu_ms": bounded_work_ms,
        "iteration_count": iteration_count,
        "checksum": checksum,
    }


def read_request_cpu_ms(query_string: str, default_ms: int) -> int:
    """쿼리 문자열의 work_ms 값을 읽어 요청별 CPU 작업 시간을 결정한다."""

    # 예: /?work_ms=300 형태로 요청하면 해당 요청만 CPU 작업 시간을 조절한다.
    values = parse_qs(query_string).get("work_ms", [])
    if not values:
        return default_ms

    # 숫자가 아닌 값은 기본값으로 되돌려 부하 테스트가 중단되지 않게 한다.
    try:
        return int(values[0])
    except ValueError:
        return default_ms


# ---------------------------------------------------------------------------
# HTTP 요청 처리
# ---------------------------------------------------------------------------

class AutoScalingDemoHandler(BaseHTTPRequestHandler):
    """ALB와 부하 테스트 요청을 처리하는 HTTP 핸들러."""

    cpu_work_ms = DEFAULT_CPU_WORK_MS
    server_version = "AutoScalingDemoHTTP/1.0"

    def do_GET(self) -> None:
        """GET 요청을 경로별로 분기해 헬스 체크 또는 부하 응답을 반환한다."""

        # 경로와 쿼리 문자열을 분리하여 헬스 체크와 일반 요청을 명확히 구분한다.
        parsed_request = urlparse(self.path)
        if parsed_request.path == "/health":
            self._send_json_response(HTTPStatus.OK, {"status": "ok"})
            return

        # 루트 경로는 CPU 작업을 수행한 뒤 인스턴스 식별 정보를 함께 반환한다.
        if parsed_request.path == "/":
            work_ms = read_request_cpu_ms(parsed_request.query, self.cpu_work_ms)
            cpu_result = run_cpu_work(work_ms)
            self._send_json_response(HTTPStatus.OK, self._build_root_response(cpu_result))
            return

        # 실습에 필요한 경로만 열어 두어 잘못된 요청을 빠르게 알아차리게 한다.
        self._send_json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "지원하지 않는 경로입니다.", "path": parsed_request.path},
        )

    def log_message(self, format_text: str, *args: Any) -> None:
        """기본 접근 로그에 요청 처리 시각과 클라이언트 주소를 남긴다."""

        # 표준 출력 기반 로그는 User data의 nohup 실행 환경에서도 확인하기 쉽다.
        now_text = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now_text}] {self.client_address[0]} - {format_text % args}")

    def _build_root_response(self, cpu_result: dict[str, int | float]) -> dict[str, object]:
        """루트 요청에 반환할 인스턴스 식별 정보와 CPU 작업 결과를 생성한다."""

        # ALB 뒤의 어떤 EC2 인스턴스가 응답했는지 CloudWatch 관찰과 함께 확인한다.
        return {
            "message": f"Hello from {socket.gethostname()}",
            "hostname": socket.gethostname(),
            "cpu": cpu_result,
            "timestamp": int(time.time()),
        }

    def _send_json_response(self, status: HTTPStatus, body: dict[str, object]) -> None:
        """딕셔너리 본문을 JSON HTTP 응답으로 직렬화해 전송한다."""

        # ensure_ascii=False로 한국어 오류 메시지를 그대로 남기되 HTTP 본문은 UTF-8로 고정한다.
        response_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)


# ---------------------------------------------------------------------------
# 서버 실행
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱해 서버 포트와 기본 CPU 작업 시간을 반환한다."""

    # EC2 User data의 `python3 app.py` 실행을 위해 기본 포트는 80으로 둔다.
    parser = argparse.ArgumentParser(description="Auto Scaling 실습용 HTTP 서버")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", DEFAULT_PORT)))
    parser.add_argument(
        "--cpu-work-ms",
        type=int,
        default=int(os.getenv("CPU_WORK_MS", DEFAULT_CPU_WORK_MS)),
        help="루트 요청마다 수행할 CPU 작업 시간(ms)",
    )
    return parser.parse_args()


def run_server() -> None:
    """ThreadingHTTPServer를 시작하고 종료 신호를 받으면 정상 종료한다."""

    # 핸들러 클래스 변수로 기본 CPU 작업 시간을 주입해 요청마다 같은 설정을 사용한다.
    args = parse_args()
    AutoScalingDemoHandler.cpu_work_ms = args.cpu_work_ms

    # 모든 네트워크 인터페이스에서 요청을 받아 ALB와 로컬 테스트를 모두 지원한다.
    server = ThreadingHTTPServer(("0.0.0.0", args.port), AutoScalingDemoHandler)
    server.timeout = 1

    # SIGTERM/SIGINT를 받으면 serve_forever 루프를 빠져나와 소켓을 정리한다.
    def request_shutdown(_signum: int, _frame: object) -> None:
        print("서버 종료 요청을 받았습니다.")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    # 서버 실행 정보를 표준 출력으로 남겨 AMI 준비 과정에서 설정을 확인한다.
    print(
        f"서버 시작: port={args.port}, "
        f"cpu_work_ms={AutoScalingDemoHandler.cpu_work_ms}"
    )
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    run_server()
