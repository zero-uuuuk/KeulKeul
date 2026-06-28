<h1 align="center">API Gateway + Lambda 실습</h1>

<p align="center">
  <code>lambda_function.py</code>는 API Gateway HTTP API 뒤에서 실행되는 Lambda 코드입니다.<br>
  route, path parameter, query string, JSON body, status code를 한 번에 확인합니다.
</p>

## 파일 구성

```text
.
├── assignment.md        # 콘솔 기반 실습 안내
├── lambda_function.py   # Lambda에 붙여넣을 Python 코드
└── README.md            # 파일 설명과 호출 예시
```

## Route 구성

| Route | 역할 |
| --- | --- |
| `GET /health` | API Gateway와 Lambda 연결 확인 |
| `GET /hello/{name}` | path parameter와 query string 확인 |
| `POST /echo` | JSON body 확인 |
| `$default` | 정의하지 않은 요청을 404로 응답 |

## 호출 예시

```bash
curl "{API_ENDPOINT}/health"
curl "{API_ENDPOINT}/hello/keulkeul?greeting=Hi"
curl -X POST "{API_ENDPOINT}/echo" \
  -H "Content-Type: application/json" \
  -d '{"message":"hello api gateway"}'
```

이번 레벨에서는 Function URL 대신 API Gateway를 Lambda 앞단에 둡니다.
