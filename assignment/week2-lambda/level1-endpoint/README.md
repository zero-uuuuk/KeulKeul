<h1 align="center">Lambda Function URL 실습</h1>

<p align="center">
  <code>lambda_function.py</code>는 AWS Lambda Function URL로 호출하는 간단한 HTTP endpoint입니다.<br>
  별도 서버, EC2, API Gateway 없이 Lambda만으로 JSON 응답을 반환합니다.
</p>

## 파일 구성

```text
.
├── assignment.md        # 콘솔 기반 실습 안내
├── lambda_function.py   # Lambda에 붙여넣을 Python 코드
└── README.md            # 파일 설명과 빠른 실행 방법
```

## 동작 방식

- `GET {FUNCTION_URL}`
  - 기본값으로 `Hello, Lambda` 메시지를 반환합니다.
- `GET {FUNCTION_URL}?name=keulkeul`
  - query string의 `name` 값을 읽어 `Hello, keulkeul` 메시지를 반환합니다.
- CloudWatch Logs
  - Lambda 실행마다 method, path, request id 로그를 남깁니다.

## Function URL 호출

Lambda 콘솔에서 Function URL을 생성한 뒤 아래처럼 호출합니다.

```bash
curl "{FUNCTION_URL}?name=keulkeul"
```

이번 레벨에서는 API Gateway를 사용하지 않습니다. API Gateway 기반 routing과 method 제어는 `level3-api-gateway`에서 다룹니다.
