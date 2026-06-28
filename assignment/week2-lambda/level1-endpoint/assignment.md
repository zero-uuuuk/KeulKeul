## Assignment: Lambda Function URL로 서버리스 endpoint 만들기

EC2나 ALB 없이 Lambda 함수 하나를 HTTP endpoint로 노출하고, 브라우저와 `curl`로 직접 호출해본다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한 (Lambda, CloudWatch Logs)
- 제공된 Lambda 코드: https://github.com/zero-uuuuk/KeulKeul/tree/main/assignment/week2-lambda/level1-endpoint/lambda_function.py

## 1. Lambda 함수 생성 (AWS 콘솔)

### 1-1. 함수 생성

1. AWS 콘솔 → **Lambda** → **함수 생성** 클릭
2. 설정값:
    - 옵션: **새로 작성**
    - 함수 이름: `keulkeul-week2-lambda`
    - 런타임: `Python 3.14`
    - 아키텍처: `x86_64`
    - 권한: **기본 Lambda 권한을 가진 새 역할 생성**
3. **함수 생성** 클릭

### 1-2. 코드 입력

1. 생성된 Lambda 함수의 **코드** 탭으로 이동
2. `lambda_function.py` 내용을 제공된 코드로 교체
3. **Deploy** 클릭

코드는 아래 정보를 응답에 포함한다.

- `message`: query string의 `name` 값을 사용한 인사 메시지 (예: `Hello, KeulKeul`)
- `method`: Function URL로 들어온 HTTP method (예: `GET`)
- `path`: 요청 path (예: `/`)
- `request_id`: Lambda 실행 요청 ID (예: `8f4b4f5a-9c7e-4c8...`)
- `timestamp`: 응답 생성 시각

## 2. Function URL 생성

Lambda 함수를 HTTP로 직접 호출하기 위한 URL을 만든다.

1. Lambda 함수 화면 → **구성** 탭 → **함수 URL** 메뉴로 이동
2. **함수 URL 생성** 클릭
3. 설정값:
    - Auth type: `NONE`
    - Configure cross-origin resource sharing (CORS): 끔
4. **저장** 클릭
5. 생성된 **함수 URL**을 복사해둔다.

> [!IMPORTANT]
> Auth type을 `NONE`으로 두면 URL을 아는 사람이 누구나 호출할 수 있다. 실습이 끝나면 반드시 리소스를 삭제한다.

## 3. endpoint 호출

로컬 터미널에서 `FUNCTION_URL`을 실제 함수 URL로 교체해 호출한다.

```bash
curl "{FUNCTION_URL}"
curl "{FUNCTION_URL}?name=keulkeul"
```

정상 응답 예시는 아래와 같다.

```json
{
  "message": "Hello, keulkeul",
  "method": "GET",
  "path": "/",
  "request_id": "00000000-0000-0000-0000-000000000000",
  "timestamp": 1760000000
}
```

브라우저 주소창에서도 같은 URL을 열어 JSON 응답을 확인한다.

## 4. CloudWatch Logs 확인

Lambda의 `print()` 출력이 어디에 저장되는지 확인한다.

1. Lambda 함수 화면 → **모니터링** 탭으로 이동
2. **CloudWatch 로그 보기** 클릭
3. 최신 Log stream을 열어 아래 형태의 로그를 확인

```text
요청 처리: method=GET, path=/, request_id=...
```

확인할 것:

- `curl`을 여러 번 실행하면 Log stream에 실행 로그가 추가되는가?
- 응답의 `request_id`와 로그의 `request_id`가 같은가?
- `?name=...` 값을 바꾸면 응답의 `message`가 바뀌는가?

## 5. 실습 질문

아래 질문에 짧게 답한다.

1. Lambda는 EC2 인스턴스처럼 계속 실행 중인 서버인가?
2. Function URL 요청에서 query string은 event의 어느 필드로 전달되는가?
3. Auth type을 `NONE`으로 둔 Function URL을 방치하면 어떤 문제가 생길 수 있는가?
4. 이번 실습에서 API Gateway를 쓰지 않아도 HTTP 호출이 가능했던 이유는 무엇인가?

## 6. 리소스 정리

실습 완료 후 아래 순서로 리소스를 삭제한다.

1. **Function URL 삭제**
    - Lambda 함수 → **구성** → **함수 URL**로 이동
    - **삭제** 클릭

2. **Lambda 함수 삭제**
    - Lambda 함수 목록에서 실습용 함수 선택
    - **작업 → 삭제** 클릭

3. **CloudWatch Log Group 확인**
    - CloudWatch 콘솔 → **로그 그룹**으로 이동
    - `/aws/lambda/keulkeul-week2-lambda` 로그 그룹이 남아 있으면 삭제

> [!NOTE]
> CloudWatch Logs는 Lambda 함수를 삭제해도 자동으로 함께 삭제되지 않을 수 있다.
