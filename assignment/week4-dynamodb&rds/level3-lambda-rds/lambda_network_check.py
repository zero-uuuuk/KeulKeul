"""RDS endpoint DNS 해석과 TCP 연결을 확인하는 Lambda 코드.

이 코드는 추가 패키지 없이 Lambda에 바로 붙여넣을 수 있다.
DB 로그인은 하지 않고, 네트워크 연결 가능 여부만 확인한다.
"""

from __future__ import annotations

import json
import os
import socket
from typing import Any


def response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Lambda proxy integration 형식의 JSON 응답을 만든다."""

    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """DB_HOST DNS 해석 후 DB_PORT로 TCP 연결을 시도한다."""

    host = os.environ.get("DB_HOST", "").strip()
    port = int(os.environ.get("DB_PORT", "3306"))
    timeout_seconds = int(os.environ.get("CONNECT_TIMEOUT_SECONDS", "2"))

    if not host:
        return response(400, {"error": "DB_HOST 환경 변수가 필요합니다."})

    try:
        address_info = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = sorted({info[4][0] for info in address_info})
    except socket.gaierror as exc:
        return response(
            500,
            {
                "message": "dns lookup failed",
                "host": host,
                "error": str(exc),
            },
        )

    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass
    except OSError as exc:
        return response(
            500,
            {
                "message": "tcp connection failed",
                "host": host,
                "port": port,
                "error": str(exc),
            },
        )

    return response(
        200,
        {
            "message": "network check ok",
            "dns": {
                "host": host,
                "addresses": addresses,
            },
            "tcp": {
                "host": host,
                "port": port,
                "connected": True,
            },
        },
    )
