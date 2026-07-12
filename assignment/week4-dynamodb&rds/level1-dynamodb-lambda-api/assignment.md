## Assignment: Lambda에서 DynamoDB 동아리 역할 API 만들기

DynamoDB Table을 만들고, Lambda 함수가 club member의 role 데이터를 저장하고 조회하도록 만든다.

참고 자료:
- https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html
- https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html
- https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html
- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.CoreComponents.html

> [!NOTE]
> 이번 레벨에서는 DynamoDB Table에 직접 item을 넣지 않는다. Table 구조만 만들고, 데이터 생성/조회/수정/삭제는 Lambda Test event로 확인한다.

> [!IMPORTANT]
> Function URL을 `Auth type: NONE`으로 만들면 URL을 아는 사람이 누구나 API를 호출할 수 있다. Function URL을 만들었다면 실습 후 삭제한다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한
    - DynamoDB
    - Lambda
    - IAM
    - CloudWatch Logs
- 제공된 Lambda 코드: `lambda_function.py`
- 제공된 IAM 정책 예시: `iam-policy-dynamodb-todos.json`
- 제공된 테스트 이벤트:
  - `events/seed_members.json`
  - `events/list_president.json`
  - `events/update_president_to_member.json`
  - `events/delete_member_hyunryeo.json`
- 실습 리전: 서울 `ap-northeast-2`

## 1. DynamoDB Table 생성

Lambda가 사용할 DynamoDB Table을 먼저 만든다.

1. AWS 콘솔 오른쪽 위 리전이 **아시아 태평양(서울) ap-northeast-2**인지 확인
2. AWS 콘솔 검색창에서 **DynamoDB** 검색
3. **DynamoDB** 서비스로 이동
4. 왼쪽 메뉴에서 **Tables** 또는 **테이블** 클릭
5. **Create table** 또는 **테이블 생성** 클릭
6. 아래 값 입력

```text
Table name: keulkeul-todos
Partition key: user_id
Partition key type: String
Sort key: todo_id
Sort key type: String
Table settings: Default settings
Capacity mode: On-demand
```

7. **Create table** 클릭
8. Table status가 `Active`가 될 때까지 기다린다.

확인할 것:

- Table 이름이 `keulkeul-todos`인가?
- Partition key가 `user_id`인가?
- Sort key가 `todo_id`인가?
- 두 key의 type이 `String`인가?
- Table status가 `Active`인가?

> [!NOTE]
> 여기서는 item을 직접 만들지 않는다. 뒤에서 Lambda Test event인 `seed_members.json`이 club member 데이터를 한 번에 넣는다.

## 2. Lambda 함수 생성

AWS Console에서 Lambda 함수를 생성한다.

1. AWS 콘솔 오른쪽 위 리전이 **아시아 태평양(서울) ap-northeast-2**인지 확인
2. AWS 콘솔 검색창에서 **Lambda** 검색
3. **Lambda** 서비스로 이동
4. **함수 생성** 클릭
5. 설정값 입력
    - 옵션: **새로 작성**
    - 함수 이름: `keulkeul-dynamodb-api`
    - 런타임: `Python 3.12` 이상 또는 콘솔에서 선택 가능한 최신 Python 런타임
    - 아키텍처: `x86_64`
    - 권한: **기본 Lambda 권한을 가진 새 역할 생성**
6. **함수 생성** 클릭

## 3. Lambda 코드 입력

1. 생성된 Lambda 함수의 **Code** 탭으로 이동
2. `lambda_function.py` 내용을 전체 복사
3. Lambda 코드 편집기의 `lambda_function.py`에 붙여넣기
4. **Deploy** 클릭

코드는 아래 작업을 처리한다.

| Method | 처리 내용 |
| --- | --- |
| `GET` | `title` 또는 `user_id` 기준 역할 item 조회 |
| `POST` | club member 역할 item 생성 |
| `PATCH` / `PUT` | 역할 title, status, name 수정 |
| `DELETE` | 역할 item 삭제 |

## 4. Lambda 실행 역할에 DynamoDB 권한 추가

Lambda가 DynamoDB Table을 읽고 쓰려면 Lambda **실행 역할**에 DynamoDB 권한이 필요하다.

### 4-1. 실행 역할 화면으로 이동

1. Lambda 함수 화면에서 **Configuration** 클릭
2. 왼쪽 메뉴 또는 상단 영역에서 **Permissions** 클릭
3. **Execution role** 영역 찾기
4. role 이름 링크 클릭
    - 예: `keulkeul-dynamodb-api-role-...`
5. 새로 열린 IAM Role 화면에서 **Permissions** 탭이 선택되어 있는지 확인

> [!IMPORTANT]
> Lambda 함수 화면의 **Resource-based policy statements**에서 추가하는 것이 아니다. 그 화면은 "누가 Lambda를 호출할 수 있는가"를 설정하는 곳이다. DynamoDB를 읽고 쓰는 권한은 Lambda의 **실행 역할**에 붙여야 한다.

### 4-2. 다른 방법: 관리형 정책 연결

 AWS가 미리 만들어둔 `AmazonDynamoDBFullAccess` 정책을 붙이면 빠르다.

현재 IAM Role의 **권한** 탭에 있다면 아래 순서대로 클릭한다.

1. 오른쪽의 **권한 추가** 버튼 클릭
2. 드롭다운에서 **정책 연결** 클릭
3. 검색창에 `AmazonDynamoDBFullAccess` 입력
4. 목록에서 `AmazonDynamoDBFullAccess` 왼쪽 체크박스 선택
5. 오른쪽 아래 또는 상단의 **권한 추가** 클릭
6. 권한 정책 목록에 `AmazonDynamoDBFullAccess`가 추가되었는지 확인

> [!NOTE]
> 이 방법은 실습용으로 가장 쉽지만 DynamoDB 전체 권한을 준다. 실제 서비스에서는 아래의 최소 권한 정책을 쓰는 것이 더 좋다.

### 4-3. 권장 방법: 인라인 정책 생성

특정 Table인 `keulkeul-todos`에만 접근하도록 최소 권한을 직접 만들 수도 있다.

현재 IAM Role의 **권한** 탭에 있다면 아래 순서대로 클릭한다.

1. 오른쪽의 **권한 추가** 버튼 클릭
2. 드롭다운에서 **인라인 정책 생성** 클릭
3. 정책 편집 화면에서 **JSON** 탭 클릭
4. 기존 예시 내용을 모두 지운다.
5. `iam-policy-dynamodb-todos.json` 파일 내용을 복사해서 붙여넣는다.
6. **다음** 클릭
7. 정책 이름 입력
    - 예: `keulkeul-dynamodb-todos-policy`
8. **정책 생성** 클릭
9. IAM Role의 권한 정책 목록에 방금 만든 정책이 보이는지 확인

붙여넣을 JSON 예시:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DynamoDbTodosTableAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:ap-northeast-2:{ACCOUNT_ID}:table/keulkeul-todos"
    }
  ]
}
```

Account ID는 ARN 가운데에 들어간다.

```text
arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{TABLE_NAME}
```
AWS 계정 ID가 다르니 {ACCOUNT_ID} ` 부분을 본인 Account ID로 바꾼다. (숫자형태)

> [!NOTE]
> `list_president` 이벤트는 `title = president` 조건으로 찾기 때문에 실습 코드에서 `Scan`을 사용한다. 실제 서비스에서는 데이터가 많아질 수 있으므로 `title` 기준 조회가 자주 필요하다면 GSI를 설계하는 것이 좋다.

## 5. 환경 변수 설정

선택 사항으로 Lambda 환경 변수를 설정한다.

1. Lambda 함수 화면 → **Configuration** → **Environment variables**
2. **Edit** 클릭
3. 아래 값 추가

```text
TABLE_NAME=keulkeul-todos
```

환경 변수를 만들지 않으면 코드가 기본값 `keulkeul-todos`를 사용한다.

## 6. Lambda Test event로 확인

Function URL을 만들기 전에 Lambda 콘솔의 Test event로 코드를 확인한다.

### 6-0. Test event 공통 설정

Lambda 콘솔에서 테스트할 때는 아래 값으로 설정한다.

1. Lambda 함수 화면에서 **Test** 탭 클릭
2. **이벤트 작업 테스트**에서 **새 이벤트 생성** 선택
3. **이벤트 공유 설정**은 **프라이빗** 선택
4. **이벤트 이름**은 아래 표처럼 입력
5. 아래의 **Event JSON** 영역에 해당 JSON 파일 내용을 붙여넣기
6. **저장** 클릭
7. **테스트** 클릭

| 실습 | 붙여넣을 파일 | 이벤트 이름 |
| --- | --- | --- |
| club member role 데이터 생성 | `events/seed_members.json` | `seed_members` |
| president 조회 | `events/list_president.json` | `list_president` |
| president를 member로 변경 | `events/update_president_to_member.json` | `update_president_to_mem` |
| Hyunryeo member item 삭제 | `events/delete_member_hyunryeo.json` | `delete_member_hyunryeo` |

### 6-1. club member role 데이터 생성

1. 새 이벤트 생성
2. 이벤트 이름: `seed_members`
3. Event JSON에 `events/seed_members.json` 내용 붙여넣기
4. **저장** 클릭
5. **테스트** 실행


생성되는 역할 데이터:

| user_id | name | title |
| --- | --- | --- |
| `younguk` | Younguk | `president` |
| `yujin` | Yujin | `vice_president` |
| `hyundo` | Hyundo | `member` |
| `juhyun` | Juhyun | `member` |
| `taeho` | Taeho | `member` |
| `munho` | Munho | `member` |
| `suha` | Suha | `member` |
| `taehwan` | Taehwan | `member` |
| `hyunryeo` | Hyunryeo | `member` |

> [!NOTE]
> `todo_id`의 `membership`은 이 item이 회원 역할 정보라는 뜻의 sort key 값이다. 실제 역할은 `title`에 들어간다.

### 6-2. president 조회

새 이벤트를 만들고 아래 값으로 실행한다.

- 붙여넣을 파일: `events/list_president.json`
- 이벤트 이름: `list_president`

확인할 것:

- `items` 배열에 DynamoDB item이 들어 있는가?
- `title`이 `president`인 item이 조회되는가?
- 조회 결과에 `younguk`이 포함되는가?

### 6-3. president를 member로 변경

새 이벤트를 만들고 아래 값으로 실행한다.

- 붙여넣을 파일: `events/update_president_to_member.json`
- 이벤트 이름: `update_president_to_mem`

확인할 것:

- `younguk`의 `title`이 `president`에서 `member`로 바뀌었는가?
- 다시 `events/list_president.json`을 실행했을 때 `younguk`이 더 이상 president로 조회되지 않는가?

### 6-4. Hyunryeo member item 삭제

새 이벤트를 만들고 아래 값으로 실행한다.

- 붙여넣을 파일: `events/delete_member_hyunryeo.json`
- 이벤트 이름: `delete_member_hyunryeo`

확인할 것:

- 응답에 `"message": "item deleted"`가 보이는가?
- DynamoDB 콘솔에서 `hyunryeo` item이 사라졌는가?



## 7. 선택 사항: Function URL 생성

Lambda Test event만으로 이번 실습의 생성/조회/수정/삭제를 모두 확인할 수 있다. 외부 URL 호출까지 보고 싶다면 Function URL을 만든다.

1. Lambda 함수 화면 → **Configuration** → **Function URL**
2. **Create function URL** 클릭
3. 설정값:
    - Auth type: `NONE`
4. 생성된 Function URL을 복사한다.
5. 브라우저 주소창에 아래 형태로 입력해 조회한다.

```text
{FUNCTION_URL}?user_id={your_name}
{FUNCTION_URL}?title=president
```

## 8. CloudWatch Logs 확인

Lambda 함수의 Monitoring 탭에서 CloudWatch Logs를 확인한다.

확인할 것:

- 요청 method와 path가 로그에 찍히는가?
- DynamoDB 권한 오류가 발생하지 않는가?
- POST 요청 후 Table에 item이 추가되는가?
- GET 요청 결과에 item이 포함되는가?

## 9. 실습 질문

아래 질문에 짧게 답한다.

1. DynamoDB에서 Partition key와 Sort key는 각각 어떤 역할을 하는가?
2. Lambda가 DynamoDB에 접근하려면 어떤 권한이 필요한가?
3. DynamoDB는 Lambda와 연결할 때 VPC 설정이 꼭 필요한가?
4. Lambda에서 `boto3`는 어떤 역할을 하는가?
5. Function URL을 `Auth type: NONE`으로 열어두면 어떤 문제가 생길 수 있는가?

## 10. 리소스 정리
Level 2에서는 RDS를 사용하므로 DynamoDB 리소스는 더 이상 필요하지 않다.

1. **Function URL 삭제**
    - Lambda 함수 → Configuration → Function URL 삭제

2. **Lambda 함수 삭제**
    - `keulkeul-dynamodb-api` 삭제

3. **IAM 실행 역할 또는 정책 삭제**
    - IAM → Roles에서 `keulkeul-dynamodb-api-role-...` 실행 역할 삭제
    - 역할을 남겨둘 경우:
        - `AmazonDynamoDBFullAccess`를 붙였다면 정책 연결 해제
        - 인라인 정책을 만들었다면 `keulkeul-dynamodb-todos-policy` 삭제

4. **DynamoDB Table 삭제**
    - `keulkeul-todos` 삭제

5. **CloudWatch Log Group 삭제**
    - `/aws/lambda/keulkeul-dynamodb-api` 로그 그룹 삭제
