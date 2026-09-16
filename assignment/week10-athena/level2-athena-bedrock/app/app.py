"""OTT 시청 이벤트를 기록하고 분석 Workflow를 실행하는 실습용 웹 서버를 띄운다."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import analysis


# ---------------------------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------------------------

DEFAULT_PORT = 8000
DEFAULT_LOG_PATH = Path(os.environ.get("LOG_PATH", "logs/view_events.json"))
INDEX_PATH = Path(__file__).resolve().parent / "index.html"

# 요청 본문 상한. 시청 이벤트 한 건은 수백 Byte라 넉넉한 값이다.
MAX_BODY_BYTES = 8_192
MAX_WATCH_MINUTES = 600

# 제공 작품 목록. weight는 Traffic Script가 작품을 고를 때 쓰는 상대 가중치다.
CATALOG: list[dict[str, Any]] = [
    {"title": "Cosmic Taxi", "genre": "sf", "weight": 25},
    {"title": "Last Call", "genre": "thriller", "weight": 18},
    {"title": "Red Signal", "genre": "action", "weight": 16},
    {"title": "Summer Letter", "genre": "romance", "weight": 13},
    {"title": "Tiny Planet", "genre": "documentary", "weight": 11},
    {"title": "Night Kitchen", "genre": "comedy", "weight": 8},
    {"title": "Blue Horizon", "genre": "drama", "weight": 5},
    {"title": "Hidden Frequency", "genre": "mystery", "weight": 4},
]
GENRE_BY_TITLE = {work["title"]: work["genre"] for work in CATALOG}
DEVICES = ["mobile", "tv", "web", "tablet"]


# ---------------------------------------------------------------------------
# 시청 로그 저장소
# ---------------------------------------------------------------------------

class EventLog:
    """시청 이벤트를 JSON Lines 파일에 기록하고 이벤트 수를 세는 저장소."""

    def __init__(self, path: Path) -> None:
        # 동시 요청 20건이 같은 파일에 쓰므로 쓰기와 카운터 갱신을 하나의 Lock으로 묶는다.
        self._lock = threading.Lock()
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # 서버를 다시 띄워도 기존 로그를 이어서 쓰도록 현재 줄 수를 세어 둔다.
        self._count = sum(1 for _ in self._path.open(encoding="utf-8")) if self._path.exists() else 0
        self._file = self._path.open("a", encoding="utf-8")

    @property
    def count(self) -> int:
        """지금까지 기록된 이벤트 수."""

        return self._count

    def append(self, event: dict[str, Any]) -> int:
        """이벤트 한 건을 한 줄로 기록하고 갱신된 전체 이벤트 수를 반환한다."""

        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            # flush를 생략하면 Buffer에 남은 로그가 S3 Snapshot에서 빠진다.
            self._file.write(line + "\n")
            self._file.flush()
            self._count += 1
            return self._count

    def snapshot(self) -> tuple[bytes, int]:
        """분석 시점의 로그 전체를 Byte로 읽어 이벤트 수와 함께 반환한다."""

        with self._lock:
            return self._path.read_bytes(), self._count


# ---------------------------------------------------------------------------
# 분석 Job 관리
# ---------------------------------------------------------------------------

class JobRunner:
    """분석 Job을 Background Thread에서 한 번에 하나씩만 실행한다."""

    def __init__(self, event_log: EventLog, config: analysis.AnalysisConfig) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._event_log = event_log
        self._config = config

    def start(self) -> dict[str, Any]:
        """새 분석 Job을 시작한다. 이미 실행 중인 Job이 있으면 그 Job을 그대로 돌려준다."""

        log_bytes, event_count = self._event_log.snapshot()
        with self._lock:
            # 버튼을 연타해도 같은 로그로 Athena Query가 중복 실행되지 않도록 진행 중인 Job을 재사용한다.
            running = next((job for job in self._jobs.values() if job["status"] == "running"), None)
            if running is not None:
                return running

            job_id = uuid.uuid4().hex[:12]
            state = analysis.create_job_state(job_id, event_count)
            self._jobs[job_id] = state

        threading.Thread(
            target=analysis.run_analysis,
            args=(state, log_bytes, self._config),
            daemon=True,
        ).start()
        return state

    def get(self, job_id: str) -> dict[str, Any] | None:
        """job_id로 Job 상태를 조회한다."""

        with self._lock:
            return self._jobs.get(job_id)


def public_job_view(state: dict[str, Any]) -> dict[str, Any]:
    """Job 상태에서 화면에 필요한 값만 추린다."""

    # title_rows·device_rows는 수십 KB가 될 수 있어 1초마다 내려보내지 않는다.
    return {key: value for key, value in state.items() if key not in ("title_rows", "device_rows")}


# ---------------------------------------------------------------------------
# 요청 본문 검증
# ---------------------------------------------------------------------------

def build_event(payload: dict[str, Any]) -> dict[str, Any]:
    """요청 본문에서 시청 이벤트를 만든다. 값이 규칙에 맞지 않으면 ValueError를 낸다."""

    # 작품 목록에 없는 title은 거부한다. genre는 서버가 정해 Athena 집계가 어긋나지 않게 한다.
    title = payload.get("title")
    if title not in GENRE_BY_TITLE:
        raise ValueError(f"등록되지 않은 작품입니다: {title!r}")

    device = payload.get("device", "web")
    if device not in DEVICES:
        raise ValueError(f"지원하지 않는 기기입니다: {device!r}")

    source = payload.get("source", "user")
    if source not in ("user", "traffic"):
        raise ValueError(f"source는 user 또는 traffic이어야 합니다: {source!r}")

    # 시청 시간은 1분 이상 상한 이하의 정수로 맞춰 Athena의 INT Column과 통계를 보호한다.
    try:
        watch_minutes = int(payload.get("watch_minutes", 0))
    except (TypeError, ValueError):
        raise ValueError("watch_minutes는 정수여야 합니다.") from None
    if not 1 <= watch_minutes <= MAX_WATCH_MINUTES:
        raise ValueError(f"watch_minutes는 1 이상 {MAX_WATCH_MINUTES} 이하여야 합니다: {watch_minutes}")

    viewer_id = str(payload.get("viewer_id", "viewer-web"))[:32]

    return {
        "event_time": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "viewer_id": viewer_id,
        "title": title,
        "genre": GENRE_BY_TITLE[title],
        "device": device,
        "watch_minutes": watch_minutes,
        "source": source,
    }


# ---------------------------------------------------------------------------
# HTTP 요청 처리
# ---------------------------------------------------------------------------

class StreamingHandler(BaseHTTPRequestHandler):
    """웹 화면과 Traffic Script의 요청을 처리하는 HTTP 핸들러."""

    server_version = "Week10StreamingHTTP/1.0"
    event_log: EventLog
    job_runner: JobRunner

    def do_GET(self) -> None:
        """GET 요청을 경로별로 분기한다."""

        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return

        if self.path in ("/", "/index.html"):
            self._send_index()
            return

        if self.path == "/api/catalog":
            self._send_json(HTTPStatus.OK, {"catalog": CATALOG, "devices": DEVICES})
            return

        if self.path == "/api/stats":
            self._send_json(HTTPStatus.OK, {"event_count": self.event_log.count})
            return

        # /api/analysis/{job_id} 형태에서 마지막 경로 조각을 job_id로 사용한다.
        if self.path.startswith("/api/analysis/"):
            state = self.job_runner.get(self.path.rsplit("/", 1)[-1])
            if state is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "존재하지 않는 job_id입니다."})
                return
            self._send_json(HTTPStatus.OK, public_job_view(state))
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "지원하지 않는 경로입니다.", "path": self.path})

    def do_POST(self) -> None:
        """POST 요청을 경로별로 분기한다."""

        if self.path == "/api/watch":
            payload = self._read_json_body()
            if payload is None:
                return
            try:
                event = build_event(payload)
            except ValueError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._send_json(HTTPStatus.OK, {"event_count": self.event_log.append(event)})
            return

        if self.path == "/api/analysis":
            if self.event_log.count == 0:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "기록된 시청 이벤트가 없습니다."})
                return
            self._send_json(HTTPStatus.ACCEPTED, public_job_view(self.job_runner.start()))
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "지원하지 않는 경로입니다.", "path": self.path})

    def log_message(self, format_text: str, *args: Any) -> None:
        """요청 로그를 표준 출력으로 남겨 journalctl에서 바로 확인하게 한다."""

        print(f"[{time.strftime('%H:%M:%S')}] {self.client_address[0]} {format_text % args}", flush=True)

    def _read_json_body(self) -> dict[str, Any] | None:
        """요청 본문을 JSON으로 읽는다. 형식이 잘못되면 오류 응답을 보내고 None을 반환한다."""

        # Content-Length가 없거나 상한을 넘는 요청은 본문을 읽지 않고 바로 거부한다.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "요청 본문 크기가 올바르지 않습니다."})
            return None

        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "JSON 본문을 해석할 수 없습니다."})
            return None

        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "요청 본문은 JSON 객체여야 합니다."})
            return None
        return payload

    def _send_index(self) -> None:
        """웹 화면 HTML을 그대로 전송한다."""

        body = INDEX_PATH.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        """Dictionary를 JSON 응답으로 직렬화해 전송한다."""

        response_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)


# ---------------------------------------------------------------------------
# 서버 실행
# ---------------------------------------------------------------------------

def main() -> None:
    """실행 인자를 읽어 웹 서버를 띄운다."""

    parser = argparse.ArgumentParser(description="Week10 OTT 시청 로그 분석 실습 서버")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    args = parser.parse_args()

    config = analysis.AnalysisConfig.from_env()
    StreamingHandler.event_log = EventLog(args.log_path)
    StreamingHandler.job_runner = JobRunner(StreamingHandler.event_log, config)

    print(f"로그 파일: {args.log_path} (기존 이벤트 {StreamingHandler.event_log.count}건)", flush=True)
    print(f"S3 Bucket: {config.bucket or '(미설정)'} / OpenAI Model: {config.openai_model}", flush=True)
    # Key 누락은 분석 마지막 단계에서야 드러나므로 서버가 뜰 때 미리 알린다.
    print(f"OPENAI_API_KEY: {'설정됨' if config.openai_api_key else '미설정 (.env 확인 필요)'}", flush=True)
    print(f"서버 시작: http://0.0.0.0:{args.port}", flush=True)

    ThreadingHTTPServer(("0.0.0.0", args.port), StreamingHandler).serve_forever()


if __name__ == "__main__":
    main()
