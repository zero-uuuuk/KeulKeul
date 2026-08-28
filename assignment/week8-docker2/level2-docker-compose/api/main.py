"""Docker Compose 실습용 Todo API.

  1. Todo 목록 조회, 생성, 수정, 삭제 API를 제공한다.
  2. PyMySQL로 Compose Network 안의 MySQL Service에 연결한다.
  3. MySQL 초기화 지연에 대응하기 위해 연결을 최대 10회 재시도한다.
"""

import os
import time
from typing import Any

import pymysql
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from pymysql.cursors import DictCursor
from pymysql.err import MySQLError

# ---------------------------------------------------------------------------
# 데이터베이스 연결 설정
# ---------------------------------------------------------------------------

DB_CONNECT_ATTEMPTS = 10
DB_RETRY_SECONDS = 2
DATABASE_CONFIG: dict[str, Any] = {
    "host": os.environ.get("DB_HOST", "db"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "database": os.environ.get("DB_NAME", "keulkeul"),
    "user": os.environ.get("DB_USER", "keulkeul_user"),
    "password": os.environ.get("DB_PASSWORD", "keulkeul_password"),
    "connect_timeout": 3,
    "cursorclass": DictCursor,
}


class TodoCreate(BaseModel):
    """Todo 생성 요청 모델."""

    title: str = Field(min_length=1, max_length=255)


class TodoUpdate(BaseModel):
    """Todo 수정 요청 모델."""

    title: str | None = Field(default=None, max_length=255)
    completed: bool | None = None


class TodoResponse(BaseModel):
    """Todo 응답 모델."""

    id: int
    title: str
    completed: bool


def connect_with_retry() -> pymysql.connections.Connection:
    """MySQL 연결을 최대 10회 시도한다."""

    for attempt in range(1, DB_CONNECT_ATTEMPTS + 1):
        try:
            return pymysql.connect(**DATABASE_CONFIG)
        except MySQLError:
            if attempt == DB_CONNECT_ATTEMPTS:
                raise
            time.sleep(DB_RETRY_SECONDS)

    raise RuntimeError("MySQL 연결 시도가 실행되지 않았다.")


# ---------------------------------------------------------------------------
# FastAPI API
# ---------------------------------------------------------------------------

app = FastAPI()


@app.get("/health")
def health_check() -> dict[str, str]:
    """FastAPI와 MySQL 연결 상태를 확인한다."""

    try:
        with connect_with_retry() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
    except MySQLError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL에 연결할 수 없습니다.",
        ) from exc

    return {"status": "ok", "database": "ok"}


@app.get("/api/todos", response_model=list[TodoResponse])
def list_todos() -> list[dict[str, Any]]:
    """모든 Todo를 ID 순서로 조회한다."""

    with connect_with_retry() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, title, completed FROM todos ORDER BY id"
            )
            rows = cursor.fetchall()

    return list(rows)


@app.post(
    "/api/todos",
    response_model=TodoResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_todo(todo: TodoCreate) -> dict[str, Any]:
    """새로운 Todo를 생성한다."""

    title = todo.title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Todo 제목은 비어 있을 수 없습니다.",
        )

    with connect_with_retry() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO todos (title, completed) VALUES (%s, %s)",
                (title, False),
            )
            todo_id = int(cursor.lastrowid)
        connection.commit()

    return {"id": todo_id, "title": title, "completed": False}


@app.patch("/api/todos/{todo_id}", response_model=TodoResponse)
def update_todo(todo_id: int, todo: TodoUpdate) -> dict[str, Any]:
    """Todo 제목 또는 완료 상태를 수정한다."""

    changes = todo.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 값이 필요합니다.",
        )

    assignments: list[str] = []
    parameters: list[Any] = []

    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Todo 제목은 비어 있을 수 없습니다.",
            )
        assignments.append("title = %s")
        parameters.append(title)

    if "completed" in changes:
        if changes["completed"] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="completed 값이 필요합니다.",
            )
        assignments.append("completed = %s")
        parameters.append(bool(changes["completed"]))

    with connect_with_retry() as connection:
        with connection.cursor() as cursor:
            parameters.append(todo_id)
            cursor.execute(
                "UPDATE todos SET "
                + ", ".join(assignments)
                + " WHERE id = %s",
                parameters,
            )
            cursor.execute(
                "SELECT id, title, completed FROM todos WHERE id = %s",
                (todo_id,),
            )
            updated_row = cursor.fetchone()
            if updated_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Todo를 찾을 수 없습니다.",
                )
            connection.commit()

    return updated_row


@app.delete("/api/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int) -> None:
    """Todo를 삭제한다."""

    with connect_with_retry() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM todos WHERE id = %s", (todo_id,))
            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Todo를 찾을 수 없습니다.",
                )
            connection.commit()
