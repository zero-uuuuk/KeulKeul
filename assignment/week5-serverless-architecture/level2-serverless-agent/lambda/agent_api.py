"""역할: OpenAI Responses API와 Notion MCP를 연결하는 Serverless Agent API를 처리한다.

상세 내용:
  1. API Gateway HTTP API event에서 route를 해석한다.
  2. Notion OAuth 연결 정보를 sessionId 기준으로 DynamoDB에 저장한다.
  3. 사용자 메시지와 assistant 답변을 DynamoDB message history에 저장한다.
  4. OpenAI Responses API 호출 중 search_agent_history function call이 나오면 History Tool Lambda를 동기 호출한다.
"""

import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib import request
from urllib.parse import quote, urlencode

import boto3
from boto3.dynamodb.conditions import Key
from openai import OpenAI


# ---------------------------------------------------------------------------
# 환경 변수 및 AWS 리소스
# ---------------------------------------------------------------------------
OPENAI_MODEL = "gpt-5.6-luna"
HISTORY_TOOL_FUNCTION = os.environ["HISTORY_TOOL_FUNCTION"]
API_BASE_URL = os.environ["API_BASE_URL"].rstrip("/")
WEB_BASE_URL = os.environ["WEB_BASE_URL"].rstrip("/")

NOTION_AUTH_URL = "https://mcp.notion.com/authorize"
NOTION_TOKEN_URL = "https://mcp.notion.com/token"
NOTION_REGISTER_URL = "https://mcp.notion.com/register"
NOTION_MCP_URL = "https://mcp.notion.com/mcp"
TTL_SECONDS = 30 * 24 * 60 * 60
MAX_AGENT_TURNS = 5

# Lambda 실행 환경에서 재사용할 AWS와 OpenAI 클라이언트 초기화
dynamodb = boto3.resource("dynamodb")
sessions_table = dynamodb.Table("keulkeul-agent-sessions")
messages_table = dynamodb.Table("keulkeul-agent-messages")
notion_connections_table = dynamodb.Table("keulkeul-agent-notion-connections")
lambda_client = boto3.client("lambda")
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ---------------------------------------------------------------------------
# 공통 응답 및 변환 유틸리티
# ---------------------------------------------------------------------------
def now_iso() -> str:
    """UTC 기준 ISO-8601 시간 문자열을 반환한다."""

    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> Any:
    """DynamoDB Decimal 값을 API Gateway JSON 응답에 맞는 숫자로 변환한다."""

    # DynamoDB Number는 Python Decimal로 반환되므로 JSON 직렬화 전에 int 또는 float로 변환
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    raise TypeError(f"{type(value).__name__} 값은 JSON으로 변환할 수 없습니다.")


def json_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """API Gateway Lambda proxy JSON 응답을 만든다."""

    # Lambda가 API Gateway에 반환해야 하는 응답 형식 구성
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body, ensure_ascii=False, default=json_default),
    }


def redirect_response(location: str) -> dict[str, Any]:
    """브라우저를 OAuth provider 또는 웹 앱으로 redirect한다."""

    # OAuth flow에서 브라우저가 다음 URL로 이동하도록 302 응답 구성
    return {
        "statusCode": 302,
        "headers": {
            "Location": location,
            "Access-Control-Allow-Origin": "*",
        },
        "body": "",
    }


# ---------------------------------------------------------------------------
# DynamoDB 세션 및 메시지 저장
# ---------------------------------------------------------------------------
def upsert_session(session_id: str, title: str) -> None:
    """session item을 생성하거나 updatedAt을 갱신한다."""

    timestamp = now_iso()
    expires_at = int(time.time()) + TTL_SECONDS # 세션 만료 시각 TTL

    # update_item은 session item이 없으면 새로 만들고 있으면 지정 필드만 갱신
    # createdAt과 title은 최초 값을 유지하고 updatedAt과 expiresAt은 매 요청마다 갱신
    sessions_table.update_item(
        Key={"sessionId": session_id},
        UpdateExpression=(
            "SET updatedAt = :updated_at, "
            "createdAt = if_not_exists(createdAt, :created_at), "
            "title = if_not_exists(title, :title), "
            "expiresAt = :expires_at"
        ),
        ExpressionAttributeValues={
            ":updated_at": timestamp,
            ":created_at": timestamp,
            ":title": title,
            ":expires_at": expires_at,
        },
    )


def save_message(
    session_id: str,
    role: str,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    """대화 메시지를 DynamoDB messages table에 저장한다."""

    timestamp = now_iso()
    expires_at = int(time.time()) + TTL_SECONDS
    message_id = uuid.uuid4().hex

    # 시간 기반 sort key로 session 안의 메시지 순서를 보존
    item = {
        "sessionId": session_id,
        "createdAtMessageId": f"{timestamp}#{message_id}",
        "messageId": message_id,
        "role": role,
        "content": content,
        "createdAt": timestamp,
        "expiresAt": expires_at,
    }

    # assistant 답변에 tool 사용 내역이 있을 때만 선택 필드 저장
    if tool_calls:
        item["toolCalls"] = tool_calls
    messages_table.put_item(Item=item)

    # 메시지 저장 후 세션 테이블의 최신 대화 상태도 함께 갱신
    sessions_table.update_item(
        Key={"sessionId": session_id},
        UpdateExpression=(
            "SET lastMessage = :last_message, updatedAt = :updated_at, expiresAt = :expires_at "
            "ADD messageCount :inc"
        ),
        ExpressionAttributeValues={
            ":last_message": content[:160],
            ":updated_at": timestamp,
            ":expires_at": expires_at,
            ":inc": 1,
        },
    )


# ---------------------------------------------------------------------------
# Notion OAuth 유틸리티
# ---------------------------------------------------------------------------
def create_code_challenge(code_verifier: str) -> str:
    """PKCE code verifier에서 S256 code challenge를 만든다."""

    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def register_notion_mcp_client() -> dict[str, Any]:
    """Notion MCP OAuth 서버에 실습용 client를 동적으로 등록한다."""

    # Notion MCP는 Dynamic Client Registration을 지원하므로 별도 Developers 앱 없이 client_id를 발급받음
    register_request = request.Request(
        NOTION_REGISTER_URL,
        data=json.dumps(
            {
                "client_name": "KeulKeul Serverless Agent",
                "client_uri": WEB_BASE_URL,
                "redirect_uris": [f"{API_BASE_URL}/notion/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": "default",
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "KeulKeul-Serverless-Agent/1.0",
        },
        method="POST",
    )

    # 등록 응답에는 callback에서 token 교환에 사용할 client_id가 포함됨
    with request.urlopen(register_request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def exchange_notion_code(code: str, client_id: str, code_verifier: str) -> dict[str, Any]:
    """Notion MCP OAuth code를 MCP access token으로 교환한다."""

    # authorization code, client_id, code_verifier를 함께 보내 MCP용 access token을 발급받음
    token_form = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": f"{API_BASE_URL}/notion/callback",
            "code_verifier": code_verifier,
        }
    )
    token_request = request.Request(
        NOTION_TOKEN_URL,
        data=token_form.encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "KeulKeul-Serverless-Agent/1.0",
        },
        method="POST",
    )

    # token 응답을 Lambda 내부 dict로 변환
    with request.urlopen(token_request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_notion_connection(session_id: str) -> dict[str, Any] | None:
    """sessionId에 연결된 Notion OAuth 정보를 조회한다."""

    # sessionId에 저장된 Notion access token과 workspace 정보를 조회
    return notion_connections_table.get_item(Key={"sessionId": session_id}).get("Item")


# ---------------------------------------------------------------------------
# OpenAI Responses API 및 function tool 처리
# ---------------------------------------------------------------------------
def call_history_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    """History Tool Lambda를 동기 호출하고 JSON 결과를 반환한다."""

    # Agent Lambda는 function tool 실행을 History Tool Lambda에 위임
    result = lambda_client.invoke(
        FunctionName=HISTORY_TOOL_FUNCTION,
        InvocationType="RequestResponse",
        Payload=json.dumps(arguments, ensure_ascii=False).encode("utf-8"),
    )
    payload = json.loads(result["Payload"].read() or "{}")
    if result.get("FunctionError"):
        return {"ok": False, "message": payload.get("errorMessage", "History Tool 실행 실패"), "items": []}
    return payload


def run_agent(session_id: str, user_message: str) -> tuple[str, list[dict[str, Any]]]:
    """OpenAI Responses API를 호출하고 필요한 function tool 결과를 이어서 전달한다."""

    # 현재 session의 전체 message history를 시간순으로 조회
    history = messages_table.query(
        KeyConditionExpression=Key("sessionId").eq(session_id),
        ScanIndexForward=True,
    )

    # Responses API에 전달할 system 지시문과 전체 대화 입력 구성
    input_messages = [
        {
            "role": "system",
            "content": (
                "너는 KeulKeul Week 5 Serverless Agent 실습 도우미다. "
                "개인 Notion 문서는 notion-search MCP tool로 찾고, 이전 대화는 search_agent_history tool로 찾고, "
                "최신 공개 정보는 web_search tool로 확인한다. 출처가 다른 정보는 구분해서 답한다."
            ),
        },
        *[
            {
                "role": item.get("role", ""),
                "content": item.get("content", ""),
            }
            for item in history.get("Items", [])
        ],
        {"role": "user", "content": user_message},
    ]
    
    # Function tool schema와 hosted web search tool 구성
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "name": "search_agent_history",
            "description": "현재 session의 이전 대화 history에서 keyword와 관련된 메시지를 검색한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sessionId": {"type": "string"},
                    "keyword": {"type": "string"},
                },
                "required": ["sessionId", "keyword"],
            },
        },
        {"type": "web_search"},
    ]

    # Notion이 연결된 session에서만 MCP tool을 노출
    connection = get_notion_connection(session_id)
    if connection and connection.get("accessToken"):
        tools.insert(
            0,
            {
                "type": "mcp",
                "server_label": "notion",
                "server_url": NOTION_MCP_URL,
                "authorization": connection["accessToken"],
                "allowed_tools": ["notion-search", "notion-fetch"],
                "require_approval": "never",
            },
        )

    used_tools: list[dict[str, Any]] = []

    # 첫 호출에서는 모델이 답변하거나 필요한 tool call을 선택
    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=input_messages,
        tools=tools,
    )

    # 모델이 function call을 멈출 때까지 관찰과 tool 실행을 반복
    for _ in range(MAX_AGENT_TURNS):
        function_outputs: list[dict[str, Any]] = []
        for item in getattr(response, "output", []) or []:
            item_type = getattr(item, "type", "")

            # OpenAI hosted web search 호출 흔적을 UI 표시용으로 기록 (실행 자체는 OpenAI가 함)
            if item_type == "web_search_call":
                used_tools.append(
                    {
                        "type": "web_search",
                        "name": "web_search",
                        "status": getattr(item, "status", ""),
                    }
                )
                continue

            # Notion Remote MCP tool 호출 흔적을 UI 표시용으로 기록 (실행 자체는 OpenAI가 함)
            if item_type == "mcp_call":
                used_tools.append(
                    {
                        "type": "mcp",
                        "name": getattr(item, "name", "mcp_call"),
                        "serverLabel": getattr(item, "server_label", ""),
                        "status": getattr(item, "status", ""),
                    }
                )
                continue
            
            # custom tool 호출 시
            if item_type == "function_call" and getattr(item, "name", "") == "search_agent_history":
                arguments = json.loads(getattr(item, "arguments", "{}") or "{}")
                arguments["sessionId"] = session_id
                tool_result = call_history_tool(arguments)
                used_tools.append({"type": "function", "name": "search_agent_history", "status": "completed"})

                # 직접 실행한 function tool 결과는 call_id와 함께 Responses API에 다시 전달 (MCP, Web Search는 OpenAI가 실행)
                function_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": getattr(item, "call_id"),
                        "output": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

        if not function_outputs:
            break

        # tool 실행 결과를 이전 response에 이어 붙여 다음 추론 턴으로 진행
        response = openai_client.responses.create(
            model=OPENAI_MODEL,
            previous_response_id=response.id,
            input=function_outputs,
            tools=tools,
        )

    # tool 호출만 남고 최종 message가 없으면 tool 없이 한 번 더 답변 생성을 요청
    if not response.output_text:
        response = openai_client.responses.create(
            model=OPENAI_MODEL,
            previous_response_id=response.id,
            input="지금까지 확인한 내용만 바탕으로 최종 답변을 작성해줘. 추가 tool은 호출하지 마.",
            tools=tools,
            tool_choice="none",
        )

    return response.output_text, used_tools


# ---------------------------------------------------------------------------
# API 라우트 처리
# ---------------------------------------------------------------------------
def handle_notion_connect(event: dict[str, Any]) -> dict[str, Any]:
    """Notion OAuth authorization URL로 redirect한다."""

    # 현재 브라우저 session을 기준으로 Notion OAuth 연결
    params = event["queryStringParameters"]
    session_id = params["sessionId"]

    # Notion 연결을 시작한 session을 생성하거나 마지막 사용 시각 갱신
    upsert_session(session_id, "Serverless Agent Chat")

    # MCP OAuth용 client와 PKCE 값을 만들고 callback 검증에 필요한 값만 서버에 저장
    client = register_notion_mcp_client()
    oauth_state = f"{session_id}.{secrets.token_urlsafe(24)}"
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = create_code_challenge(code_verifier)
    timestamp = now_iso()
    expires_at = int(time.time()) + TTL_SECONDS
    notion_connections_table.put_item(
        Item={
            "sessionId": session_id,
            "connected": False,
            "oauthState": oauth_state,
            "codeVerifier": code_verifier,
            "mcpClientId": client["client_id"],
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "expiresAt": expires_at,
        }
    )

    # sessionId를 포함한 state와 PKCE challenge를 담아 Notion MCP 로그인 및 권한 승인 화면으로 이동
    redirect_uri = quote(f"{API_BASE_URL}/notion/callback", safe="") # 권한 승인이 끝난 뒤, 다시 돌아올 API 주소
    return redirect_response(
        f"{NOTION_AUTH_URL}"
        f"?client_id={client['client_id']}"
        f"&response_type=code"
        f"&scope=default"
        f"&redirect_uri={redirect_uri}"
        f"&state={quote(oauth_state, safe='')}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&prompt=consent"
    )


def handle_notion_callback(event: dict[str, Any]) -> dict[str, Any]:
    """Notion OAuth callback을 처리하고 access token을 저장한다."""

    # Notion이 돌려준 code와 state 값을 callback query string에서 추출
    params = event["queryStringParameters"]
    code = params["code"]
    oauth_state = params["state"]
    session_id = oauth_state.split(".", 1)[0]
    connection = get_notion_connection(session_id)
    if not connection or connection.get("oauthState") != oauth_state:
        return json_response(400, {"message": "Notion OAuth state가 올바르지 않습니다."})

    # authorization code를 MCP access token으로 변환
    token = exchange_notion_code(code, connection["mcpClientId"], connection["codeVerifier"])
    timestamp = now_iso()
    expires_at = int(time.time()) + TTL_SECONDS
    
    # 노션 커넥션 테이블에 sessionId 기준으로 MCP token 저장
    notion_connections_table.put_item(
        Item={
            "sessionId": session_id,
            "connected": True,
            "accessToken": token["access_token"],
            "refreshToken": token.get("refresh_token", ""),
            "tokenType": token.get("token_type", "Bearer"),
            "workspaceName": token.get("workspace_id", "Notion"),
            "userId": token.get("user_id", ""),
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "expiresAt": expires_at,
        }
    )
  
    # 웹 첫 화면으로 돌려보냄
    return redirect_response(f"{WEB_BASE_URL}/?sessionId={session_id}&notion=connected")


def handle_notion_status(event: dict[str, Any]) -> dict[str, Any]:
    """현재 session의 Notion 연결 상태를 반환한다."""

    # 현재 session의 Notion 연결 상태 조회
    session_id = event["queryStringParameters"]["sessionId"]
    connection = get_notion_connection(session_id)
    if not connection:
        return json_response(200, {"connected": False})
    return json_response(
        200,
        {
            "connected": bool(connection.get("connected")),
            "workspaceName": connection.get("workspaceName", "Notion"),
        },
    )


def handle_chat(event: dict[str, Any]) -> dict[str, Any]:
    """사용자 메시지를 저장하고 Agent 답변을 생성한다."""

    # API Gateway body를 JSON payload로 변환
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    payload = json.loads(body)
    session_id = payload["sessionId"]
    message = payload["message"].strip()
    if not message:
        return json_response(400, {"message": "message가 필요합니다."})

    upsert_session(session_id, title=message[:40])  # 세션 생성 또는 최신 상태 갱신
    save_message(session_id, "user", message)  # 사용자 메시지 저장
    answer, used_tools = run_agent(session_id, message)  # Agent 답변 생성
    save_message(session_id, "assistant", answer, used_tools)  # assistant 답변과 tool 사용 내역 저장

    return json_response(
        200,
        {
            "sessionId": session_id,
            "answer": answer,
            "usedTools": used_tools,
        },
    )


def handle_list_sessions() -> dict[str, Any]:
    """저장된 session 목록을 반환한다."""

    # 실습용 화면에서 보여줄 session 목록 조회
    result = sessions_table.scan()
    return json_response(200, {"items": result.get("Items", [])})


def handle_list_messages(event: dict[str, Any]) -> dict[str, Any]:
    """특정 session의 message history를 시간순으로 반환한다."""

    # API Gateway path parameter에서 조회할 sessionId를 가져옴
    session_id = (event.get("pathParameters") or {}).get("sessionId", "")
    if not session_id:
        return json_response(400, {"message": "sessionId가 필요합니다."})

    # 선택한 session의 전체 메시지를 시간순으로 조회
    result = messages_table.query(
        KeyConditionExpression=Key("sessionId").eq(session_id),
        ScanIndexForward=True,
    )
    return json_response(200, {"items": result.get("Items", [])})


# ---------------------------------------------------------------------------
# Lambda 진입점
# ---------------------------------------------------------------------------
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """HTTP method와 path에 맞는 handler로 요청을 라우팅한다."""

    # API Gateway HTTP API event에서 route 판별에 필요한 값 추출
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "").upper()
    path = event.get("rawPath", "")

    # 브라우저 CORS preflight 요청은 실제 handler 실행 없이 종료
    if method == "OPTIONS":
        return json_response(200, {"ok": True})

    try:
        # HTTP API route를 내부 handler 함수로 연결
        if method == "GET" and path.endswith("/notion/connect"):
            return handle_notion_connect(event)
        if method == "GET" and path.endswith("/notion/callback"):
            return handle_notion_callback(event)
        if method == "GET" and path.endswith("/notion/status"):
            return handle_notion_status(event)
        if method == "POST" and path.endswith("/agent/chat"):
            return handle_chat(event)
        if method == "GET" and path.endswith("/agent/sessions"):
            return handle_list_sessions()
        if method == "GET" and path.endswith("/messages"):
            return handle_list_messages(event)
        return json_response(404, {"message": "지원하지 않는 API 경로입니다."})
    except Exception as error:
        return json_response(500, {"message": str(error)})
