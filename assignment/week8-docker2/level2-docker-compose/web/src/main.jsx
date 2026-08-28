import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const responseText = await response.text();
  const data = responseText ? JSON.parse(responseText) : null;

  if (!response.ok) {
    const detail = data && data.detail ? data.detail : "요청에 실패했습니다.";
    throw new Error(detail);
  }

  return data;
}

function App() {
  const [todos, setTodos] = useState([]);
  const [newTitle, setNewTitle] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadTodos() {
    try {
      setError("");
      const data = await request("/api/todos");
      setTodos(data);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTodos();
  }, []);

  async function handleCreate(event) {
    event.preventDefault();
    if (!newTitle.trim()) {
      setError("Todo 제목을 입력하세요.");
      return;
    }

    try {
      setError("");
      const todo = await request("/api/todos", {
        method: "POST",
        body: JSON.stringify({ title: newTitle }),
      });
      setTodos((currentTodos) => [...currentTodos, todo]);
      setNewTitle("");
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function handleToggle(todo) {
    try {
      setError("");
      const updatedTodo = await request("/api/todos/" + todo.id, {
        method: "PATCH",
        body: JSON.stringify({ completed: !todo.completed }),
      });
      setTodos((currentTodos) =>
        currentTodos.map((currentTodo) =>
          currentTodo.id === updatedTodo.id ? updatedTodo : currentTodo
        )
      );
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  function startEditing(todo) {
    setEditingId(todo.id);
    setEditingTitle(todo.title);
    setError("");
  }

  function cancelEditing() {
    setEditingId(null);
    setEditingTitle("");
  }

  async function saveEditing(todoId) {
    if (!editingTitle.trim()) {
      setError("Todo 제목을 입력하세요.");
      return;
    }

    try {
      setError("");
      const updatedTodo = await request("/api/todos/" + todoId, {
        method: "PATCH",
        body: JSON.stringify({ title: editingTitle }),
      });
      setTodos((currentTodos) =>
        currentTodos.map((currentTodo) =>
          currentTodo.id === updatedTodo.id ? updatedTodo : currentTodo
        )
      );
      cancelEditing();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function handleDelete(todoId) {
    try {
      setError("");
      await request("/api/todos/" + todoId, { method: "DELETE" });
      setTodos((currentTodos) =>
        currentTodos.filter((currentTodo) => currentTodo.id !== todoId)
      );
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">KeulKeul Week 8</p>
        <h1>Docker Compose Todo</h1>
        <p className="description">
          React + Vite Web, FastAPI API, MySQL Database를 하나의 Compose 환경으로
          실행합니다.
        </p>
      </section>

      <section className="todo-card">
        <form className="create-form" onSubmit={handleCreate}>
          <label htmlFor="new-title">새 Todo</label>
          <div className="create-row">
            <input
              id="new-title"
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              placeholder="Todo 제목을 입력하세요"
            />
            <button type="submit">추가</button>
          </div>
        </form>

        {error && <p className="error" role="alert">{error}</p>}

        {loading ? (
          <p className="empty">Todo를 불러오는 중입니다.</p>
        ) : todos.length === 0 ? (
          <p className="empty">등록된 Todo가 없습니다.</p>
        ) : (
          <ul className="todo-list">
            {todos.map((todo) => (
              <li
                className={"todo-item" + (todo.completed ? " completed" : "")}
                key={todo.id}
              >
                {editingId === todo.id ? (
                  <div className="edit-row">
                    <input
                      value={editingTitle}
                      onChange={(event) => setEditingTitle(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          void saveEditing(todo.id);
                        }
                      }}
                    />
                    <button type="button" onClick={() => void saveEditing(todo.id)}>
                      저장
                    </button>
                    <button type="button" className="secondary" onClick={cancelEditing}>
                      취소
                    </button>
                  </div>
                ) : (
                  <>
                    <label className="todo-label">
                      <input
                        type="checkbox"
                        checked={todo.completed}
                        onChange={() => void handleToggle(todo)}
                      />
                      <span>{todo.title}</span>
                    </label>
                    <div className="actions">
                      <button type="button" className="secondary" onClick={() => startEditing(todo)}>
                        수정
                      </button>
                      <button type="button" className="danger" onClick={() => void handleDelete(todo.id)}>
                        삭제
                      </button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);

