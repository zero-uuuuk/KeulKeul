"""MySQL RDS에 연결해 SELECT 1 또는 club_members 조회를 실행하는 Lambda 코드.

이 코드는 PyMySQL dependency가 필요하다.
requirements.txt와 함께 zip package로 만들어 Lambda에 업로드한다.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

import pymysql


def json_default(value: Any) -> str:
    """datetime 값을 JSON 문자열로 변환한다."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Lambda proxy integration 형식의 JSON 응답을 만든다."""

    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False, default=json_default),
    }


def get_required_env(name: str) -> str:
    """필수 환경 변수를 읽고 비어 있으면 명확한 오류를 발생시킨다."""

    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} 환경 변수가 필요합니다.")
    return value


def get_query_params(event: dict[str, Any]) -> dict[str, str]:
    """Lambda Test event 또는 Function URL의 query string을 반환한다."""

    return event.get("queryStringParameters") or {}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """RDS MySQL에 접속해 SELECT 1 또는 title 조회를 실행한다."""

    try:
        host = get_required_env("DB_HOST")
        port = int(os.environ.get("DB_PORT", "3306"))
        database = get_required_env("DB_NAME")
        user = get_required_env("DB_USER")
        password = get_required_env("DB_PASSWORD")
    except ValueError as exc:
        return response(400, {"error": str(exc)})

    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
        )

        with connection:
            with connection.cursor() as cursor:
                query_params = get_query_params(event)
                title = query_params.get("title")

                if title:
                    cursor.execute(
                        """
                        SELECT *
                        FROM club_members
                        WHERE title = %s
                        ORDER BY id
                        """,
                        (title,),
                    )
                    rows = cursor.fetchall()
                    return response(
                        200,
                        {
                            "message": "club members loaded",
                            "title": title,
                            "count": len(rows),
                            "items": rows,
                        },
                    )

                cursor.execute("SELECT 1 AS value")
                row = cursor.fetchone()

    except pymysql.MySQLError as exc:
        return response(
            500,
            {
                "message": "db query failed",
                "error": str(exc),
            },
        )

    return response(
        200,
        {
            "message": "select 1 ok",
            "result": row,
        },
    )
