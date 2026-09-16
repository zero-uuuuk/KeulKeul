"""시청 로그를 S3에 올리고 Athena로 집계한 뒤 OpenAI 리포트를 생성한다."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

import boto3
from botocore.exceptions import BotoCoreError, ClientError


# ---------------------------------------------------------------------------
# 실행 설정
# ---------------------------------------------------------------------------

# Athena Query 한 건이 이 시간을 넘기면 실패로 처리해 Job이 영원히 매달리지 않게 한다.
ATHENA_TIMEOUT_SECONDS = 180
ATHENA_POLL_INTERVAL_SECONDS = 1.0

# Prompt가 지나치게 길어지지 않도록 집계 결과에서 사용할 Row 수를 제한한다.
MAX_PROMPT_ROWS = 100

# OpenAI Chat Completions Endpoint와 요청 Timeout.
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_TIMEOUT_SECONDS = 120

# 분석 Workflow의 단계 정의. 화면의 진행 상태 목록도 이 순서를 그대로 따른다.
STEP_DEFINITIONS: list[tuple[str, str]] = [
    ("s3_upload", "S3 Upload"),
    ("create_table", "Athena Table 생성"),
    ("run_query", "Athena Query 실행"),
    ("ai_report", "AI 분석"),
]


@dataclass(frozen=True)
class AnalysisConfig:
    """분석 Workflow가 사용하는 AWS Resource 이름 모음."""

    region: str
    bucket: str
    database: str
    table: str
    athena_output: str
    openai_model: str
    openai_api_key: str

    @property
    def s3_key(self) -> str:
        """Athena External Table이 바라보는 view-events/ 경로의 로그 파일 Key."""

        return "view-events/view_events.json"

    @property
    def qualified_table(self) -> str:
        """Query에서 사용할 `database.table` 형식의 전체 Table 이름."""

        return f"{self.database}.{self.table}"

    @classmethod
    def from_env(cls) -> "AnalysisConfig":
        """Environment Variable에서 설정을 읽는다. 값이 없으면 실습 기본값을 사용한다."""

        bucket = os.environ.get("S3_BUCKET", "")
        region = os.environ.get("AWS_REGION", "ap-northeast-2")
        return cls(
            region=region,
            bucket=bucket,
            database=os.environ.get("ATHENA_DATABASE", "week10_streaming"),
            table=os.environ.get("ATHENA_TABLE", "view_events"),
            # 기본값은 Bucket 이름에서 유도해 Environment Variable 하나를 덜 설정하게 한다.
            athena_output=os.environ.get("ATHENA_OUTPUT", f"s3://{bucket}/athena-results/"),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
            # .env 파일은 systemd의 EnvironmentFile이 읽어 Process 환경에 넣어 준다.
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        )


# ---------------------------------------------------------------------------
# Job State
# ---------------------------------------------------------------------------

def create_job_state(job_id: str, event_count: int) -> dict[str, Any]:
    """분석 Job 하나의 초기 상태를 만든다. 웹 화면은 이 Dictionary를 그대로 JSON으로 받는다."""

    return {
        "job_id": job_id,
        "status": "running",
        "event_count": event_count,
        "started_at": time.time(),
        "steps": [
            {"name": name, "label": label, "state": "pending", "detail": {}, "error": None}
            for name, label in STEP_DEFINITIONS
        ],
        "report": None,
    }


def _find_step(state: dict[str, Any], name: str) -> dict[str, Any]:
    """단계 이름으로 Job State 안의 단계 Dictionary를 찾는다."""

    return next(step for step in state["steps"] if step["name"] == name)


def _run_step(state: dict[str, Any], name: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """한 단계를 실행하며 진행 중·성공·실패 상태와 중간 결과를 Job State에 기록한다."""

    step = _find_step(state, name)
    step["state"] = "running"
    try:
        detail = action()
    except (ClientError, BotoCoreError, RuntimeError, OSError) as error:
        # AWS 오류 메시지는 권한·Model 접근 문제를 그대로 담고 있어 화면에 노출하는 편이 디버깅에 낫다.
        step["state"] = "failed"
        step["error"] = str(error)
        state["status"] = "failed"
        raise

    step["state"] = "succeeded"
    step["detail"] = detail
    return detail


# ---------------------------------------------------------------------------
# Athena 실행 헬퍼
# ---------------------------------------------------------------------------

def _execute_athena(athena: Any, sql: str, config: AnalysisConfig) -> str:
    """Athena Query를 시작하고 끝날 때까지 기다린 뒤 Query Execution ID를 반환한다."""

    # DDL과 SELECT 모두 Database를 SQL에 직접 명시하므로 QueryExecutionContext를 쓰지 않는다.
    query_execution_id = athena.start_query_execution(
        QueryString=sql,
        ResultConfiguration={"OutputLocation": config.athena_output},
    )["QueryExecutionId"]

    # Athena는 비동기 실행이라 상태를 직접 Polling해야 한다.
    deadline = time.monotonic() + ATHENA_TIMEOUT_SECONDS
    while True:
        status = athena.get_query_execution(QueryExecutionId=query_execution_id)["QueryExecution"]["Status"]
        query_state = status["State"]
        if query_state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        if time.monotonic() > deadline:
            raise RuntimeError(f"Athena Query가 {ATHENA_TIMEOUT_SECONDS}초 안에 끝나지 않았습니다: {query_execution_id}")
        time.sleep(ATHENA_POLL_INTERVAL_SECONDS)

    if query_state != "SUCCEEDED":
        reason = status.get("StateChangeReason", "원인 정보 없음")
        raise RuntimeError(f"Athena Query {query_state}: {reason}")

    return query_execution_id


def rows_from_result_pages(pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Athena GetQueryResults 응답 Page들을 Column 이름을 Key로 갖는 Dictionary 목록으로 바꾼다."""

    # SELECT 결과는 첫 Page의 첫 Row만 Column 이름이고, 이후 Page에는 Header가 없다.
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for page in pages:
        for row in page["ResultSet"]["Rows"]:
            values = [cell.get("VarCharValue", "") for cell in row["Data"]]
            if header is None:
                header = values
                continue
            rows.append(dict(zip(header, values)))
    return rows


def _fetch_rows(athena: Any, query_execution_id: str) -> list[dict[str, str]]:
    """Query 결과 전체를 Paginator로 읽어 Dictionary 목록으로 반환한다."""

    paginator = athena.get_paginator("get_query_results")
    pages = list(paginator.paginate(QueryExecutionId=query_execution_id))
    return rows_from_result_pages(pages)


# ---------------------------------------------------------------------------
# Prompt 구성
# ---------------------------------------------------------------------------

def _format_rows(rows: list[dict[str, str]]) -> str:
    """집계 Row 목록을 Model에 넘길 Pipe 구분 표 형태의 Text로 바꾼다."""

    if not rows:
        return "(결과 없음)"

    limited = rows[:MAX_PROMPT_ROWS]
    header = list(limited[0].keys())
    lines = [" | ".join(header)]
    lines.extend(" | ".join(row.get(column, "") for column in header) for row in limited)
    if len(rows) > MAX_PROMPT_ROWS:
        lines.append(f"(이하 {len(rows) - MAX_PROMPT_ROWS}행 생략)")
    return "\n".join(lines)


def build_prompt(title_rows: list[dict[str, str]], device_rows: list[dict[str, str]], event_count: int) -> str:
    """Athena 집계 결과와 분석 요청 사항을 하나의 한국어 Prompt로 합친다."""

    return f"""당신은 OTT 서비스의 데이터 분석가입니다. 아래는 Amazon Athena로 집계한 시청 로그입니다.
전체 이벤트 수는 {event_count}건입니다.
source 값이 user면 실제 사용자가 브라우저에서 직접 선택한 이벤트이고, traffic이면 부하 생성 Script가 만든 이벤트입니다.

[작품·장르별 집계]
{_format_rows(title_rows)}

[기기별 집계]
{_format_rows(device_rows)}

다음 조건에 맞춰 한국어 분석 리포트를 작성하세요.
- 실제 사용자와 Traffic Script 데이터를 구분해 분석하세요.
- 인기 작품과 장르, 주요 기기, 평균 시청 시간을 요약하세요.
- 데이터에 근거한 콘텐츠 운영 제안 두 개를 작성하세요.
- 실제 사용자 이벤트가 적으면 결과를 일반화할 수 없다고 명시하세요.

아래 구조의 Markdown으로 작성하세요.
## 핵심 요약
## 실제 사용자가 많이 선택한 작품
## Traffic 데이터의 작품·장르·기기 분포
## 콘텐츠 운영 제안
"""


# ---------------------------------------------------------------------------
# OpenAI 호출
# ---------------------------------------------------------------------------

def _openai_request(url: str, api_key: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """OpenAI API에 요청을 보내고 JSON 응답을 반환한다. 실패하면 응답 본문을 담은 RuntimeError를 낸다."""

    # AWS와 달리 OpenAI는 Instance Profile 같은 자동 자격증명 경로가 없다. Key를 직접 Header에 넣는다.
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=OPENAI_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # 401은 Key 오류, 429는 잔액이나 Rate Limit 문제다. 본문을 그대로 보여 주는 편이 원인 파악이 빠르다.
        detail = error.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"OpenAI 호출 실패 (HTTP {error.code}): {detail}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"OpenAI 연결 실패: {error}") from None


def call_openai(prompt: str, config: AnalysisConfig) -> str:
    """Prompt를 Chat Completions API에 보내고 생성된 리포트 Text를 반환한다."""

    # Key가 비어 있으면 401을 받기 전에 먼저 멈춰, .env 설정 누락임을 화면에 분명히 알린다.
    if not config.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인한다.")

    # max_tokens와 temperature는 Model 세대마다 허용 값이 달라 보내지 않는다. 기본값으로 충분하다.
    payload = {
        "model": config.openai_model,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _openai_request(OPENAI_URL, config.openai_api_key, payload)

    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as error:
        raise RuntimeError(f"OpenAI 응답 형식이 예상과 다릅니다: {error}") from None


# ---------------------------------------------------------------------------
# 분석 Workflow
# ---------------------------------------------------------------------------

def run_analysis(state: dict[str, Any], log_bytes: bytes, config: AnalysisConfig) -> None:
    """S3 Upload부터 AI 리포트까지를 순서대로 실행하며 Job State를 갱신한다."""

    session = boto3.session.Session(region_name=config.region)
    event_count = state["event_count"]

    # 1단계: 분석 시점의 로그 Snapshot을 Athena가 읽는 경로에 그대로 올린다.
    def upload() -> dict[str, Any]:
        session.client("s3").put_object(
            Bucket=config.bucket,
            Key=config.s3_key,
            Body=log_bytes,
            ContentType="application/json",
        )
        return {
            "event_count": event_count,
            "size_bytes": len(log_bytes),
            "s3_uri": f"s3://{config.bucket}/{config.s3_key}",
        }

    # 2단계: Glue Crawler 없이 DDL로 Database와 External Table Metadata를 직접 등록한다.
    def create_table() -> dict[str, Any]:
        athena = session.client("athena")
        _execute_athena(athena, f"CREATE DATABASE IF NOT EXISTS {config.database}", config)
        _execute_athena(athena, _create_table_sql(config), config)
        return {"database": config.database, "table": config.table}

    # 3단계: 작품·장르별 집계와 기기별 집계를 각각 실행한다.
    def run_query() -> dict[str, Any]:
        athena = session.client("athena")
        title_query_id = _execute_athena(athena, _title_query_sql(config), config)
        device_query_id = _execute_athena(athena, _device_query_sql(config), config)
        state["title_rows"] = _fetch_rows(athena, title_query_id)
        state["device_rows"] = _fetch_rows(athena, device_query_id)
        return {
            "title_query_id": title_query_id,
            "device_query_id": device_query_id,
            "row_count": len(state["title_rows"]) + len(state["device_rows"]),
        }

    # 4단계: 집계 결과를 OpenAI Chat Completions API에 넘겨 한국어 리포트를 받는다.
    def ai_report() -> dict[str, Any]:
        prompt = build_prompt(state["title_rows"], state["device_rows"], event_count)
        state["report"] = call_openai(prompt, config)
        return {"model": config.openai_model}

    try:
        _run_step(state, "s3_upload", upload)
        _run_step(state, "create_table", create_table)
        _run_step(state, "run_query", run_query)
        _run_step(state, "ai_report", ai_report)
    except Exception:
        # 실패한 단계 정보는 _run_step이 이미 기록했으므로 Job은 여기서 조용히 끝낸다.
        return

    state["status"] = "succeeded"


# ---------------------------------------------------------------------------
# SQL 문자열
# ---------------------------------------------------------------------------

def _create_table_sql(config: AnalysisConfig) -> str:
    """JSON Lines 로그를 읽는 External Table DDL을 만든다."""

    # LOCATION은 파일이 아니라 Prefix를 가리킨다. athena-results/를 같은 Prefix에 두면 안 된다.
    return f"""CREATE EXTERNAL TABLE IF NOT EXISTS {config.qualified_table} (
    event_time STRING,
    viewer_id STRING,
    title STRING,
    genre STRING,
    device STRING,
    watch_minutes INT,
    source STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://{config.bucket}/view-events/'
TBLPROPERTIES ('ignore.malformed.json' = 'true')"""


def _title_query_sql(config: AnalysisConfig) -> str:
    """source별로 작품과 장르의 시청 수, 평균 시청 시간을 집계한다."""

    return f"""SELECT source, title, genre,
       COUNT(*) AS view_count,
       ROUND(AVG(watch_minutes), 1) AS average_watch_minutes
FROM {config.qualified_table}
GROUP BY source, title, genre
ORDER BY source, view_count DESC"""


def _device_query_sql(config: AnalysisConfig) -> str:
    """source별 접속 기기 분포를 집계한다."""

    return f"""SELECT source, device, COUNT(*) AS view_count
FROM {config.qualified_table}
GROUP BY source, device
ORDER BY source, view_count DESC"""


# ---------------------------------------------------------------------------
# 자체 점검
# ---------------------------------------------------------------------------

def _self_check() -> None:
    """AWS 호출 없이 결과 Parsing과 Prompt 구성 로직이 맞는지 확인한다."""

    # Athena는 첫 Page 첫 Row에만 Column 이름을 담아 보내므로 그 규칙을 그대로 재현해 검증한다.
    def cell_row(*values: str) -> dict[str, Any]:
        return {"Data": [{"VarCharValue": value} for value in values]}

    pages = [
        {"ResultSet": {"Rows": [cell_row("source", "title"), cell_row("user", "Cosmic Taxi")]}},
        {"ResultSet": {"Rows": [cell_row("traffic", "Red Signal")]}},
    ]
    rows = rows_from_result_pages(pages)
    assert rows == [
        {"source": "user", "title": "Cosmic Taxi"},
        {"source": "traffic", "title": "Red Signal"},
    ], rows

    # NULL Column은 VarCharValue 자체가 없으므로 빈 문자열로 채워져야 한다.
    null_pages = [{"ResultSet": {"Rows": [cell_row("source", "title"), {"Data": [{"VarCharValue": "user"}, {}]}]}}]
    assert rows_from_result_pages(null_pages) == [{"source": "user", "title": ""}]

    # 결과가 Header 한 줄뿐이면 빈 목록이어야 한다.
    assert rows_from_result_pages([{"ResultSet": {"Rows": [cell_row("source")]}}]) == []

    prompt = build_prompt(rows, [], 2)
    assert "Cosmic Taxi" in prompt and "(결과 없음)" in prompt and "전체 이벤트 수는 2건" in prompt

    config = AnalysisConfig.from_env()
    assert config.qualified_table.count(".") == 1

    # Key가 없을 때 401을 받으러 가지 않고 먼저 멈추는지 확인한다.
    import dataclasses

    keyless = dataclasses.replace(config, openai_api_key="")
    try:
        call_openai("ping", keyless)
        raise AssertionError("Key가 없는데도 호출을 시도했다")
    except RuntimeError as error:
        assert "OPENAI_API_KEY" in str(error), error

    print("self-check 통과")


if __name__ == "__main__":
    _self_check()
