"""역할: Docker Image 실습용 FastAPI 애플리케이션.

상세 내용:
  1. 루트 경로 요청을 처리한다.
  2. Docker Container에서 실행할 JSON 응답을 반환한다.
  3. 별도 상태나 외부 의존성은 사용하지 않는다.
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root() -> dict[str, str]:
    """Docker Container에서 제공할 인사 메시지를 반환한다."""
    return {"message": "Hello from KeulKeul Docker"}
