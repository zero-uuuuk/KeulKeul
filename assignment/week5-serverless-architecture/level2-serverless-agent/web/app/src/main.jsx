import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "https://{본인_API_ID}.execute-api.{REGION}.amazonaws.com";
const SESSION_KEY = "keulkeul-agent-session-id";
const PLACEHOLDER_API = API_BASE.includes("{본인_API_ID}");

const quickPrompts = [
  "내 Notion에서 agent 실습 기준을 찾아줘.",
  "방금 내가 무엇을 물어봤는지 history에서 찾아줘.",
  "최신 Lambda 환경 변수 보안 권장사항도 같이 정리해줘.",
];

const toolLabels = {
  notion: "Notion MCP",
  "notion.search": "Notion search",
  "notion.fetch": "Notion fetch",
  "notion-search": "Notion search",
  "notion-fetch": "Notion fetch",
  search_agent_history: "History tool",
  web_search: "Web search",
};

function generateSessionId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  if (globalThis.crypto?.getRandomValues) {
    const values = new Uint32Array(4);
    globalThis.crypto.getRandomValues(values);
    return Array.from(values, (value) => value.toString(16).padStart(8, "0")).join("-");
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function createSessionId() {
  const existing = localStorage.getItem(SESSION_KEY);
  if (existing) {
    return existing;
  }

  const nextId = generateSessionId();
  localStorage.setItem(SESSION_KEY, nextId);
  return nextId;
}

function compactSessionId(sessionId) {
  return `${sessionId.slice(0, 8)}...${sessionId.slice(-4)}`;
}

function toolText(tool) {
  if (typeof tool === "string") {
    return toolLabels[tool] || tool;
  }

  const name = tool?.name || tool?.type || "tool";
  return toolLabels[name] || name;
}

function toolStatus(tool) {
  if (!tool || typeof tool === "string") {
    return "";
  }
  return tool.status || "completed";
}

function nowTime() {
  return new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

async function assertOk(response) {
  if (response.ok) {
    return response;
  }

  const body = await response.json().catch(() => ({}));
  throw new Error(body.message || `HTTP ${response.status}`);
}

async function requestJson(path, options = {}) {
  const response = await assertOk(await fetch(`${API_BASE}${path}`, options));
  return response.json();
}

function Message({ item }) {
  const isUser = item.role === "user";
  const tools = item.usedTools || item.toolCalls || [];

  return (
    <article className={`message ${isUser ? "userMessage" : "assistantMessage"}`}>
      <div className="messageMeta">
        <span>{isUser ? "User" : "Agent"}</span>
        {item.createdAt && <time>{new Date(item.createdAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}</time>}
      </div>
      <p>{item.content || item.answer}</p>
      {tools.length > 0 && (
        <div className="toolChips">
          {tools.map((tool, index) => (
            <span key={`${toolText(tool)}-${index}`}>{toolText(tool)}</span>
          ))}
        </div>
      )}
    </article>
  );
}

function App() {
  const [sessionId, setSessionId] = useState(() => createSessionId());
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [input, setInput] = useState("");
  const [notice, setNotice] = useState(PLACEHOLDER_API ? "API Gateway Invoke URL을 연결하면 실제 Agent와 대화할 수 있습니다." : "Agent 상태를 확인하는 중입니다.");
  const [notionStatus, setNotionStatus] = useState({ connected: false });
  const [activityLog, setActivityLog] = useState([{ at: nowTime(), text: "Agent console 준비" }]);
  const [activePanel, setActivePanel] = useState("status");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  function addLog(text) {
    setActivityLog((items) => [{ at: nowTime(), text }, ...items].slice(0, 18));
  }

  const toolSummary = useMemo(() => {
    return messages.flatMap((item) => item.usedTools || item.toolCalls || []);
  }, [messages]);

  const toolNames = useMemo(() => toolSummary.map(toolText), [toolSummary]);
  const activeTools = notionStatus.connected
    ? ["Notion MCP", "History tool", "Web search"]
    : ["History tool", "Web search"];

  async function loadNotionStatus(targetSessionId = sessionId) {
    if (PLACEHOLDER_API) {
      return;
    }

    const body = await requestJson(`/notion/status?sessionId=${encodeURIComponent(targetSessionId)}`);
    setNotionStatus(body);
  }

  async function loadMessages(targetSessionId = sessionId) {
    if (PLACEHOLDER_API) {
      return;
    }

    const body = await requestJson(`/agent/sessions/${encodeURIComponent(targetSessionId)}/messages`);
    setMessages(body.items || []);
  }

  async function loadSessions() {
    if (PLACEHOLDER_API) {
      return;
    }

    const body = await requestJson("/agent/sessions");
    setSessions(body.items || []);
  }

  async function refreshAll(targetSessionId = sessionId) {
    await Promise.all([
      loadNotionStatus(targetSessionId),
      loadMessages(targetSessionId),
      loadSessions(),
    ]);
    setNotice("최신 session 상태를 불러왔습니다.");
    addLog("session 상태 새로고침");
  }

  function selectSession(nextSessionId) {
    localStorage.setItem(SESSION_KEY, nextSessionId);
    setSessionId(nextSessionId);
    setMessages([]);
    addLog(`session 전환: ${compactSessionId(nextSessionId)}`);
    refreshAll(nextSessionId).catch((error) => setNotice(error.message));
  }

  function createNewSession() {
    const nextSessionId = generateSessionId();
    localStorage.setItem(SESSION_KEY, nextSessionId);
    setSessionId(nextSessionId);
    setMessages([]);
    setNotionStatus({ connected: false });
    setNotice("새 session을 만들었습니다.");
    addLog(`새 session 생성: ${compactSessionId(nextSessionId)}`);
  }

  function connectNotion() {
    if (PLACEHOLDER_API) {
      setNotice("먼저 API_BASE 또는 VITE_API_BASE에 API Gateway Invoke URL을 입력하세요.");
      return;
    }

    addLog("Notion MCP OAuth 연결 시작");
    window.location.href = `${API_BASE}/notion/connect?sessionId=${encodeURIComponent(sessionId)}`;
  }

  async function sendMessage(event) {
    event.preventDefault();
    const content = input.trim();
    if (!content) {
      return;
    }
    if (PLACEHOLDER_API) {
      setNotice("API Gateway Invoke URL을 연결한 뒤 메시지를 보낼 수 있습니다.");
      return;
    }

    setBusy(true);
    setInput("");
    setMessages((items) => [...items, { role: "user", content, createdAt: new Date().toISOString() }]);
    setNotice("Agent가 tool을 고르는 중입니다.");
    addLog("사용자 메시지 저장 요청");

    try {
      const body = await requestJson("/agent/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sessionId, message: content }),
      });

      if (body.sessionId && body.sessionId !== sessionId) {
        localStorage.setItem(SESSION_KEY, body.sessionId);
        setSessionId(body.sessionId);
      }

      setMessages((items) => [
        ...items,
        {
          role: "assistant",
          content: body.answer,
          usedTools: body.usedTools || [],
          createdAt: new Date().toISOString(),
        },
      ]);
      for (const tool of body.usedTools || []) {
        addLog(`${toolText(tool)} 호출 완료`);
      }
      await loadSessions();
      setNotice("Agent 답변을 저장했습니다.");
      addLog("assistant 답변 저장");
    } catch (error) {
      setNotice(error.message);
      addLog(`오류: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshAll().catch((error) => setNotice(error.message));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages]);

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">KeulKeul Week 5</p>
          <h1>Serverless Agent</h1>
        </div>
        <div className="topActions">
          <button className="ghostButton" onClick={() => refreshAll().catch((error) => setNotice(error.message))} type="button">
            새로고침
          </button>
          <button onClick={createNewSession} type="button">
            새 session
          </button>
        </div>
      </header>

      <section className="workspace">
        <section className="chatPanel">
          <div className="chatHead">
            <div>
              <h2>Chat</h2>
              <p>{notice}</p>
            </div>
            <span className={busy ? "stateBadge loading" : "stateBadge connected"}>
              {busy ? "thinking" : "online"}
            </span>
          </div>

          <div className="quickPrompts" aria-label="빠른 질문">
            {quickPrompts.map((prompt) => (
              <button key={prompt} onClick={() => setInput(prompt)} type="button">
                {prompt}
              </button>
            ))}
          </div>

          <div className="messageList" aria-live="polite">
            {messages.length === 0 && (
              <div className="emptyState">
                <h2>첫 질문을 보내세요</h2>
                <p>Notion 문서, 이전 대화 history, 최신 웹 정보를 한 번에 묶어 답변하는 흐름을 확인할 수 있습니다.</p>
              </div>
            )}
            {messages.map((item, index) => (
              <Message item={item} key={`${item.createdAt || index}-${index}`} />
            ))}
            {busy && (
              <article className="message assistantMessage loadingMessage">
                <div className="messageMeta">
                  <span>Agent</span>
                  <time>{nowTime()}</time>
                </div>
                <div className="typingRows" aria-label="Agent 진행 상황">
                  <span />
                  <span />
                  <span />
                </div>
              </article>
            )}
            <div ref={scrollRef} />
          </div>

          <form className="composer" onSubmit={sendMessage}>
            <textarea
              onChange={(event) => setInput(event.target.value)}
              placeholder="내 Notion 기준과 방금 대화, 최신 웹 정보를 합쳐서 체크리스트를 만들어줘."
              rows="3"
              value={input}
            />
            <button disabled={busy || !input.trim()} type="submit">
              {busy ? "처리 중" : "보내기"}
            </button>
          </form>
        </section>

        <aside className="analysisPanel" aria-label="분석 패널">
          <div className="sideHead">
            <div>
              <h2>Agent Monitor</h2>
              <p className="muted">채팅 흐름에 맞춰 필요한 정보만 확인</p>
            </div>
            <span className={busy ? "stateBadge loading" : "stateBadge connected"}>
              {busy ? "진행 중" : "대기"}
            </span>
          </div>

          <div className="tabBar" role="tablist" aria-label="Agent 정보 전환">
            {[
              ["status", "상태"],
              ["tools", "Tools"],
              ["logs", "Logs"],
              ["sessions", "Sessions"],
            ].map(([key, label]) => (
              <button
                aria-selected={activePanel === key}
                className={activePanel === key ? "tabButton activeTab" : "tabButton"}
                key={key}
                onClick={() => setActivePanel(key)}
                role="tab"
                type="button"
              >
                {label}
              </button>
            ))}
          </div>

          <div className="sideContent">
            {activePanel === "status" && (
              <>
                <section className="sideSection notionPanel">
                  <div className="panelHead">
                    <div>
                      <h2>Notion</h2>
                      <p className="muted">{notionStatus.workspaceName || "개인 workspace 연결"}</p>
                    </div>
                    <span className={notionStatus.connected ? "stateBadge connected" : "stateBadge disconnected"}>
                      {notionStatus.connected ? "연결됨" : "대기"}
                    </span>
                  </div>
                  <button className="wideButton" onClick={connectNotion} type="button">
                    Notion 연결
                  </button>
                </section>

                <section className="sideSection">
                  <div className="panelHead">
                    <h2>진행 상황</h2>
                    <span className={busy ? "stateBadge loading" : "stateBadge connected"}>
                      {busy ? "진행 중" : "대기"}
                    </span>
                  </div>
                  <ol className="progressList" aria-label="Agent 진행 상황">
                    <li className={messages.length > 0 ? "done" : "pending"}>session 동기화</li>
                    <li className={busy ? "active" : toolSummary.length > 0 ? "done" : "pending"}>tool 선택</li>
                    <li className={busy ? "active" : messages.some((item) => item.role === "assistant") ? "done" : "pending"}>답변 저장</li>
                  </ol>
                </section>

                <section className="sideSection">
                  <div className="panelHead">
                    <h2>Runtime</h2>
                    <span className="countText">{messages.length}</span>
                  </div>
                  <div className="metricGrid">
                    <div>
                      <span>Session</span>
                      <strong>{compactSessionId(sessionId)}</strong>
                    </div>
                    <div>
                      <span>Messages</span>
                      <strong>{messages.length}</strong>
                    </div>
                    <div>
                      <span>Available tools</span>
                      <strong>{activeTools.length}</strong>
                    </div>
                    <div>
                      <span>Calls</span>
                      <strong>{toolNames.length}</strong>
                    </div>
                  </div>
                </section>
              </>
            )}

            {activePanel === "tools" && (
              <>
                <section className="sideSection">
                  <div className="panelHead">
                    <h2>Tool Calls</h2>
                    <span className="countText">{toolSummary.length}</span>
                  </div>
                  <div className="toolCallList">
                    {toolSummary.length === 0 && <p className="emptyText">아직 호출된 tool이 없습니다.</p>}
                    {toolSummary.map((tool, index) => (
                      <div className="toolCallItem" key={`${toolText(tool)}-${index}`}>
                        <strong>{toolText(tool)}</strong>
                        <span>{toolStatus(tool)}</span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="sideSection">
                  <div className="panelHead">
                    <h2>Available</h2>
                    <span className="countText">{activeTools.length}</span>
                  </div>
                  <div className="toolList">
                    {activeTools.map((tool) => (
                      <span key={tool}>{tool}</span>
                    ))}
                  </div>
                </section>
              </>
            )}

            {activePanel === "logs" && (
              <section className="sideSection">
                <div className="panelHead">
                  <h2>Logs</h2>
                  <span className="countText">{activityLog.length}</span>
                </div>
                <ol className="logList">
                  {activityLog.map((item, index) => (
                    <li key={`${item.at}-${item.text}-${index}`}>
                      <time>{item.at}</time>
                      <span>{item.text}</span>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {activePanel === "sessions" && (
              <section className="sideSection sessionPanel">
                <div className="panelHead">
                  <h2>Sessions</h2>
                  <span className="countText">{sessions.length}</span>
                </div>
                <div className="sessionList">
                  {sessions.length === 0 && <p className="emptyText">아직 저장된 session이 없습니다.</p>}
                  {sessions.map((item) => (
                    <button
                      className={`sessionItem ${item.sessionId === sessionId ? "activeSession" : ""}`}
                      key={item.sessionId}
                      onClick={() => selectSession(item.sessionId)}
                      type="button"
                    >
                      <strong>{item.title || compactSessionId(item.sessionId)}</strong>
                      <span>{item.lastMessage || "대화 기록 없음"}</span>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
