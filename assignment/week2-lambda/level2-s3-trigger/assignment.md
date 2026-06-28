## Assignment: S3 업로드 이벤트로 Lambda 자동 실행하기

S3 버킷에 파일을 업로드하면 Lambda가 자동 실행되고, 업로드된 객체 정보를 CloudWatch Logs에서 확인한다.

참고 자료: https://inpa.tistory.com/entry/AWS-%F0%9F%93%9A-%EB%9E%8C%EB%8B%A4Lambda-%EC%8B%A4%EC%A0%84-%EA%B5%AC%EC%B6%95%ED%95%98%EA%B8%B0?category=947446

> [!NOTE]
> 이번 레벨에서는 HTTP endpoint를 만들지 않는다. Lambda는 S3 Event Notification을 통해 비동기로 실행된다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한 (Lambda, S3, CloudWatch Logs)
- 제공된 Lambda 코드: https://github.com/zero-uuuuk/KeulKeul/tree/main/assignment/week2-lambda/level2-s3-trigger/lambda_function.py
- Lambda 함수와 S3 버킷은 같은 리전에 생성한다.

## 1. S3 버킷 생성 (AWS 콘솔)

> [!IMPORTANT]
> S3(Simple Storage Service)는 파일을 객체(object) 단위로 저장하는 AWS 객체 저장소다. 파일을 담는 최상위 공간을 버킷(bucket), 업로드된 개별 파일을 객체(object), 객체의 경로와 이름을 key라고 부른다.

1. AWS 콘솔 → **S3** → **버킷 만들기** 클릭
2. 설정값:
    - 버킷 이름: 전 세계에서 고유한 이름 입력 (예: `keulkeul-lambda-practice-bucket`)
    - AWS 리전: Lambda 함수와 같은 리전 선택 (저는 항상 `us-east-2`에서 모든 작업을 합니다.)
    - 객체 소유권, 퍼블릭 액세스 차단, 버킷 버전 관리: 기본값 유지
3. **버킷 만들기** 클릭

> [!IMPORTANT]
> 이번 실습 버킷은 public으로 열 필요가 없다. 퍼블릭 액세스 차단은 켜둔다.

## 2. Lambda 함수 생성

### 2-1. 함수 생성

1. AWS 콘솔 → **Lambda** → **함수 생성** 클릭
2. 설정값:
    - 옵션: **새로 작성**
    - 함수 이름: `keulkeul-week2-lambda-s3-trigger`
    - 런타임: `Python 3.14`
    - 아키텍처: `x86_64`
    - 권한: **기본 Lambda 권한을 가진 새 역할 생성**
3. **함수 생성** 클릭

### 2-2. 코드 입력

1. 생성된 Lambda 함수의 **코드** 탭으로 이동
2. `lambda_function.py` 내용을 제공된 코드로 교체
3. **Deploy** 클릭

코드는 S3 이벤트에서 아래 값을 읽어 로그로 남긴다.

- `bucket`: 파일이 업로드된 S3 버킷 이름
- `key`: 업로드된 객체 key
- `size`: 객체 크기
- `event`: S3 이벤트 이름
- `request_id`: Lambda 실행 요청 ID

## 3. S3 trigger 추가

Lambda 함수가 S3 업로드 이벤트로 실행되도록 trigger를 연결한다.

1. Lambda 함수 화면 → **함수 개요** → **트리거 추가** 클릭
2. 설정값:
    - 소스: `S3`
    - 버킷: 1장에서 만든 버킷 선택
    - 이벤트 유형: `모든 객체 생성 이벤트`
    - Prefix: 비워둠
    - Suffix: 비워둠
3. 재귀 호출 경고를 확인하고 체크한다.
4. **추가** 클릭

> [!NOTE]
> Prefix와 Suffix는 S3 객체 key 기준 필터다. 예를 들어 Prefix를 `images/`, Suffix를 `.png`로 설정하면 `images/cat.png`는 Lambda를 실행하지만 `images/cat.jpg`나 `logs/cat.png`는 실행하지 않는다. 이번 실습에서는 모든 업로드를 확인하기 위해 둘 다 비워둔다.

> [!IMPORTANT]
> Lambda가 같은 버킷에 다시 파일을 업로드하면 자기 자신을 계속 실행할 수 있다. 이번 코드는 S3에 다시 쓰지 않고 로그만 남긴다.

## 4. 파일 업로드로 실행 확인

1. S3 콘솔 → 실습 버킷으로 이동
2. **업로드** 클릭
3. 임의의 작은 파일을 선택해 업로드
    - 예: `sample.txt`, `hello image.png`
4. Lambda 함수 화면 → **모니터링** → **CloudWatch 로그 보기** 클릭
5. 최신 Log stream에서 아래 형태의 로그를 확인

```text
S3 객체 이벤트: bucket=..., key=sample.txt, size=..., event=ObjectCreated:Put, request_id=...
```

확인할 것:

- 파일을 업로드할 때마다 Lambda 로그가 추가되는가?
- 공백이 있는 파일명을 올렸을 때 `key`가 사람이 읽을 수 있게 표시되는가?
- `event` 값이 `ObjectCreated:Put` 또는 객체 생성 계열 이벤트로 보이는가?

> [!NOTE]
> S3 Event Notification은 최소 한 번 전달되는 방식이다. 보통은 업로드 한 번에 Lambda가 한 번 실행되지만, 같은 업로드 이벤트 때문에 Lambda가 두 번 이상 실행될 수도 있다. 이번 실습은 로그만 남기므로 중복 실행되어도 문제 없다.

## 5. S3 event 구조 확인

S3가 Lambda에 전달하는 event의 핵심 구조는 아래와 같다.

```json
{
  "Records": [
    {
      "eventName": "ObjectCreated:Put",
      "s3": {
        "bucket": {
          "name": "실습버킷이름"
        },
        "object": {
          "key": "sample.txt",
          "size": 123
        }
      }
    }
  ]
}
```

이번 코드에서는 `event["Records"][0]["s3"]["object"]["key"]` 흐름으로 업로드된 객체 key를 읽는다.

## 6. 실습 질문

아래 질문에 짧게 답한다.

1. S3 trigger는 동기식 호출인가, 비동기식 호출인가?
2. 업로드된 파일명은 event의 어느 필드에서 확인할 수 있는가?
3. Lambda가 같은 S3 버킷에 파일을 다시 업로드하면 어떤 문제가 생길 수 있는가?
4. S3 trigger를 추가하면 Lambda의 resource-based policy에는 어떤 권한이 추가되는가?

## 7. 리소스 정리

실습 완료 후 아래 순서로 리소스를 삭제한다.

1. **S3 trigger 삭제**
    - Lambda 함수 → **구성** → **트리거**로 이동
    - 실습용 S3 trigger 선택 후 삭제

2. **Lambda 함수 삭제**
    - Lambda 함수 목록에서 실습용 함수 선택
    - **작업 → 삭제** 클릭

3. **S3 객체 및 버킷 삭제**
    - S3 버킷에서 업로드한 객체 삭제
    - 버킷 비우기 후 버킷 삭제

4. **CloudWatch Log Group 확인**
    - CloudWatch 콘솔 → **로그 그룹**으로 이동
    - `/aws/lambda/keulkeul-week2-lambda-s3-trigger` 로그 그룹이 남아 있으면 삭제
