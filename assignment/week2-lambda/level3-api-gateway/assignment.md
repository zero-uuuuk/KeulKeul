## Assignment: API Gateway로 Lambda API route 구성하기

API Gateway HTTP API를 Lambda 앞단에 두고, 여러 route를 하나의 Lambda 함수로 처리한다.

참고 자료:
- https://inpa.tistory.com/entry/AWS-%F0%9F%93%9A-API-Gateway-%EA%B0%9C%EB%85%90-%EA%B8%B0%EB%B3%B8-%EC%82%AC%EC%9A%A9%EB%B2%95-%EC%A0%95%EB%A6%AC
- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html
- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-routes.html

> [!NOTE]
> 이번 레벨에서는 Lambda Function URL을 사용하지 않는다. 클라이언트 요청은 API Gateway endpoint로 들어오고, API Gateway가 route에 맞는 Lambda integration을 실행한다.

> [!IMPORTANT]
> API Gateway는 API의 입구 역할을 하는 AWS 서비스다. HTTP method와 path를 기준으로 요청을 route에 매칭하고, 인증, 배포 stage, 로깅, throttling(초당 요청 수 제한) 같은 API 운영 기능을 Lambda 앞단에 둘 수 있다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한 (Lambda, API Gateway, CloudWatch Logs)
- 제공된 Lambda 코드: https://github.com/zero-uuuuk/KeulKeul/tree/main/assignment/week2-lambda/level3-api-gateway/lambda_function.py
- Lambda 함수와 API Gateway는 같은 리전에 생성한다.

## 1. Lambda 함수 생성

### 1-1. 함수 생성

1. AWS 콘솔 → **Lambda** → **함수 생성** 클릭
2. 설정값:
    - 옵션: **새로 작성**
    - 함수 이름: `keulkeul-week2-api-gateway`
    - 런타임: `Python 3.14`
    - 아키텍처: `x86_64`
    - 권한: **기본 Lambda 권한을 가진 새 역할 생성**
3. **함수 생성** 클릭

### 1-2. 코드 입력

1. 생성된 Lambda 함수의 **코드** 탭으로 이동
2. `lambda_function.py` 내용을 제공된 코드로 교체
3. **Deploy** 클릭

코드는 API Gateway 이벤트에서 아래 값을 읽는다.

- `routeKey`: API Gateway가 선택한 route (예: `GET /hello/{name}`)
- `requestContext.http.method`: HTTP method (예: `GET`)
- `requestContext.http.path`: 요청 path (예: `/hello/keulkeul`)
- `pathParameters`: path parameter (예: `{"name": "keulkeul"}`)
- `queryStringParameters`: query string (예: `{"greeting": "Hi"}`)
- `body`: POST 요청의 JSON body

## 2. HTTP API 생성 (API Gateway 콘솔)

1. AWS 콘솔 → **API Gateway** → **API 생성** 클릭
2. **HTTP API** 선택 후 **Build** 클릭
3. Integration 설정:
    - Integration type: `Lambda`
    - Lambda function: `keulkeul-week2-api-gateway`
4. API 이름: `keulkeul-week2-http-api`
5. **다음** 클릭

> [!NOTE]
> HTTP API는 Lambda와 HTTP backend를 빠르게 연결하기 위한 단순하고 저렴한 API Gateway 유형이다. REST API는 더 많은 고급 기능을 제공하지만 이번 실습 범위에는 HTTP API로 충분하다.

## 3. Route 구성

아래 route를 모두 같은 Lambda integration에 연결한다.

| Method | Path | 확인할 내용 |
| --- | --- | --- |
| `GET` | `/health` | API와 Lambda 연결 상태 |
| `GET` | `/hello/{name}` | path parameter와 query string |
| `POST` | `/echo` | JSON request body |
| `$default` | - | 정의하지 않은 요청의 404 응답 |

> [!NOTE]
> 같은 Lambda integration에 연결한다는 것은 여러 route가 모두 `keulkeul-week2-api-gateway` Lambda 함수를 실행한다는 뜻이다. Lambda 코드는 API Gateway가 넘겨준 `routeKey` 값을 보고 route별 로직을 분기한다.

> [!NOTE]
> API Gateway에서 Lambda integration을 연결하면 API Gateway가 Lambda를 호출하는 설정이 함께 만들어진다. 따라서 S3 실습처럼 Lambda 화면에서 trigger를 따로 추가하지 않아도 된다.

콘솔에서 route를 추가할 때:

1. **Routes** 단계에서 **Add route** 클릭
2. 위 표의 method와 path를 각각 입력
3. 각 route의 integration으로 `keulkeul-week2-api-gateway` Lambda 선택
4. `$default` route도 같은 Lambda integration에 연결 (따로 조작없이도 연결되어있음)
5. **다음** 클릭

> [!NOTE]
> `/hello/{name}`의 `{name}`은 path parameter다. 예를 들어 `/hello/keulkeul`로 호출하면 Lambda event의 `pathParameters.name` 값이 `keulkeul`이 된다.

## 4. Stage 생성

Stage는 배포된 API의 실행 환경 이름이다. 예를 들어 `dev`, `prod`처럼 환경을 나눌 수 있고, 이번 실습의 `$default` stage는 URL에 stage 이름을 붙이지 않는 기본 배포 환경이다.

1. Stage는 `$default` 사용
2. Auto-deploy: 켬
3. **생성** 클릭
4. 생성 완료 후 API의 **Invoke URL**을 복사해둔다.

> [!NOTE]
> Auto-deploy가 켜져 있으면 route 변경 후 별도 배포 버튼을 누르지 않아도 최신 설정이 endpoint에 반영된다.

## 5. API 호출

로컬 터미널에서 `API_ENDPOINT`를 실제 Invoke URL로 교체해 호출한다.

### 5-1. health route

```bash
curl "{API_ENDPOINT}/health"
```

정상 응답 예시:

```json
{
  "status": "ok",
  "request_id": "00000000-0000-0000-0000-000000000000"
}
```

### 5-2. path parameter와 query string

```bash
curl "{API_ENDPOINT}/hello/keulkeul?greeting=Hi"
```

정상 응답 예시:

```json
{
  "message": "Hi, keulkeul",
  "name": "keulkeul",
  "greeting": "Hi",
  "request_id": "00000000-0000-0000-0000-000000000000"
}
```

> [!NOTE]
> zsh에서는 `?`가 wildcard로 해석될 수 있으므로 URL 전체를 따옴표로 감싼다.

### 5-3. POST JSON body

```bash
curl -X POST "{API_ENDPOINT}/echo" \
  -H "Content-Type: application/json" \
  -d '{"message":"hello api gateway"}'
```

정상 응답 예시:

```json
{
  "message": "echo",
  "body": {
    "message": "hello api gateway"
  },
  "request_id": "00000000-0000-0000-0000-000000000000"
}
```

### 5-4. 정의하지 않은 route

```bash
curl "{API_ENDPOINT}/unknown"
```

`$default` route가 Lambda로 요청을 보내고, Lambda가 `404` 응답을 반환한다.

## 6. CloudWatch Logs 확인

Lambda의 `print()` 출력이 어디에 저장되는지 확인한다.

1. Lambda 함수 화면 → **모니터링** 탭으로 이동
2. **CloudWatch 로그 보기** 클릭
3. 최신 Log stream에서 아래 형태의 로그를 확인

```text
API 요청: route=GET /hello/{name}, method=GET, path=/hello/keulkeul, request_id=...
```

확인할 것:

- `/health`, `/hello/{name}`, `/echo` 호출마다 route 값이 다르게 찍히는가?
- `/hello/keulkeul?greeting=Hi`에서 `name`과 `greeting`이 응답에 반영되는가?
- 잘못된 JSON body를 보내면 `400` 응답이 오는가?
- 정의하지 않은 route는 `404` 응답을 반환하는가?

## 7. 실습 질문

아래 질문에 짧게 답한다.

1. Function URL과 API Gateway의 차이는 무엇인가?
2. API Gateway HTTP API에서 route는 어떤 두 요소로 구성되는가?
3. `/hello/{name}`에서 `keulkeul` 값은 Lambda event의 어느 필드로 전달되는가?
4. `POST /echo` 요청의 JSON body는 Lambda event의 어느 필드로 전달되는가?
5. `$default` route는 언제 사용되는가?

## 8. 리소스 정리

실습 완료 후 아래 순서로 리소스를 삭제한다.

1. **API Gateway 삭제**
    - API Gateway 콘솔 → 실습용 API 선택
    - **작업 → 삭제** 클릭

2. **Lambda 함수 삭제**
    - Lambda 함수 목록에서 `keulkeul-week2-api-gateway` 선택
    - **작업 → 삭제** 클릭

3. **CloudWatch Log Group 삭제**
    - CloudWatch 콘솔 → **로그 그룹**으로 이동
    - `/aws/lambda/keulkeul-week2-api-gateway` 로그 그룹 삭제
