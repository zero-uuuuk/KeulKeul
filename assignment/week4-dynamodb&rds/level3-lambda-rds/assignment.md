## Assignment: Lambda에서 RDS 연결 단계별 확인하기

Lambda가 RDS에 연결할 때 어떤 지점에서 실패할 수 있는지 단계별로 확인한다.

참고 자료:
- https://docs.aws.amazon.com/lambda/latest/dg/services-rds.html
- https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ConnectToInstance.html
- https://pymysql.readthedocs.io/en/latest/

> [!NOTE]
> 이번 레벨의 목표는 완성형 CRUD API가 아니다. Lambda가 RDS endpoint를 찾고, port까지 연결하고, DB에 로그인하고, SQL을 실행하는 과정을 나눠서 확인하는 것이다.

> [!IMPORTANT]
> DynamoDB는 Lambda 실행 역할의 IAM 권한과 AWS SDK로 접근했다. RDS는 실제 DB 서버에 접속하는 구조라서 endpoint, port, username, password, DB driver, VPC, Security Group을 함께 확인해야 한다.

## 0. 사전 준비

- Level 2에서 만든 RDS DB instance
- RDS endpoint
- RDS port
    - MySQL: `3306`
- database name
    - 예: `keulkeul`
- DB username/password
- RDS Security Group
    - 예: `keulkeul-rds-sg`
- 제공된 파일:
  - `lambda_network_check.py`
  - `lambda_function.py`
  - `requirements.txt`
  - `events/select1.json`
  - `events/find_vice_president.json`

## 1. RDS에 club member table 만들기

Level 2에서 이미 `club_members` Table을 만들었다면 새로 만들지 않고 그대로 사용한다.

먼저 DB client에서 아래 SQL을 실행해서 Table이 있는지 확인한다.

```sql
SHOW TABLES LIKE 'club_members';
```

Table이 있으면 데이터도 확인한다.

```sql
SELECT id, user_id, name, title, status
FROM club_members
ORDER BY id;
```

`club_members` Table이 없으면 Level 2의 SQL 파일을 실행한다.

```text
assignment/week4-dynamodb&rds/level2-rds-sql/sql/mysql_members.sql
```

확인할 것:

- `club_members` Table이 있는가?
- `Younguk`은 `president`인가?
- `Yujin`은 `vice_president`인가?
- 나머지 멤버들은 `member`인가?

## 2. Lambda가 RDS 문 앞까지 갈 수 있는지 확인

여기서는 DB 로그인을 하지 않는다. Lambda가 RDS endpoint의 주소를 찾고, DB port까지 TCP 연결을 만들 수 있는지만 확인한다.

확인하는 것:

- DNS 확인
- TCP connection 확인

### 2-1. 네트워크 체크 Lambda 만들기

1. AWS 콘솔 → **Lambda** → **함수 생성**
2. 설정값 입력
    - 옵션: **새로 작성**
    - 함수 이름: `keulkeul-rds-network-check`
    - 런타임: `Python 3.12` 이상 또는 콘솔에서 선택 가능한 최신 Python 런타임
    - 아키텍처: `x86_64`
    - 권한: **기본 Lambda 권한을 가진 새 역할 생성**
3. **함수 생성** 클릭
4. **Code** 탭에서 `lambda_network_check.py` 내용을 전체 붙여넣기
5. **Deploy** 클릭

> [!NOTE]
> 2번에서는 `lambda_network_check.py`를 사용한다. 이 코드는 DNS와 TCP 연결만 확인한다. `lambda_function.py`는 3번에서 DB username/password로 로그인하고 SQL을 실행할 때 사용한다.

### 2-2. Lambda 제한 시간 설정

네트워크 연결 확인은 기본 3초 timeout으로는 실패할 수 있다.

1. Lambda 함수 화면 → **Configuration** → **General configuration**
2. **Edit** 클릭
3. Timeout을 `10 sec`로 변경
4. **Save** 클릭

### 2-3. 환경 변수 입력

1. Lambda 함수 화면 → **Configuration** → **Environment variables**
2. **Edit** 클릭
3. 아래 값을 추가

```text
DB_HOST=본인 RDS endpoint
DB_PORT=3306
CONNECT_TIMEOUT_SECONDS=2
```

예:

```text
DB_HOST=keulkeul-db.xxxxxxxxxxxx.ap-northeast-2.rds.amazonaws.com
DB_PORT=3306
CONNECT_TIMEOUT_SECONDS=2
```

### 2-4. Lambda 실행 역할에 VPC 권한 추가

Lambda를 VPC에 연결하려면 Lambda가 VPC 안에 네트워크 인터페이스를 만들 수 있어야 한다.

1. Lambda 함수 화면 → **Configuration** → **Permissions**
2. **Execution role** 링크 클릭
3. IAM Role 화면에서 **Permissions** 탭 클릭
4. **Add permissions** → **Attach policies** 클릭
5. `AWSLambdaVPCAccessExecutionRole` 검색
6. 체크 후 **Add permissions** 클릭

아래 오류가 나오면 이 권한이 없는 것이다.

```text
The provided execution role does not have permissions to call CreateNetworkInterface on EC2
```

### 2-5. VPC와 Security Group 확인

Lambda가 RDS와 같은 VPC 안에서 접근하는 구조라면 아래를 확인한다.

1. Lambda 함수 화면 → **Configuration** → **VPC**
2. **Edit** 클릭
3. RDS와 같은 VPC 선택
    - 예: Level 2에서 RDS를 만들 때 생성된 VPC
4. RDS와 같은 VPC의 subnet 선택
    - 실습에서는 1개 subnet만 보여도 선택하고 진행한다.
    - 콘솔의 "2개 이상 subnet 권장" 문구는 고가용성 권장 사항이다.
5. Security Group 선택
    - 실습에서는 `keulkeul-rds-sg`를 선택한다.
6. **Save** 클릭
7. RDS Security Group으로 이동
8. **Inbound rules**에 아래 규칙 추가
    - Type: `MYSQL/Aurora`
    - Port: `3306`
    - Source: `keulkeul-rds-sg`

> [!NOTE]
> RDS Security Group의 Source에 `keulkeul-rds-sg`를 넣으면, 같은 Security Group을 가진 Lambda가 RDS의 MySQL port로 들어올 수 있게 허용한다는 뜻이다.
> Source가 `My IP`만 있으면 내 PC에서는 접속할 수 있지만 Lambda에서는 `tcp connection failed` 또는 `timed out`이 날 수 있다.

### 2-6. 테스트 실행

Lambda **Test** 탭에서 새 이벤트를 만들고 아무 JSON이나 넣어 실행한다. 예시는 `events/select1.json`을 그대로 사용해도 된다.

정상 응답 예시:

```json
{
  "message": "network check ok",
  "dns": {
    "host": "keulkeul-db.xxxxxxxxxxxx.ap-northeast-2.rds.amazonaws.com",
    "addresses": [
      "10.0.12.34"
    ]
  },
  "tcp": {
    "host": "keulkeul-db.xxxxxxxxxxxx.ap-northeast-2.rds.amazonaws.com",
    "port": 3306,
    "connected": true
  }
}
```

확인할 것:

- `dns.addresses`가 보이는가?
- `tcp.connected`가 `true`인가?

오류가 날 때:

| 오류 | 원인 | 해결 |
| --- | --- | --- |
| `Task timed out after 3.00 seconds` | Lambda timeout이 기본 3초라 네트워크 체크가 끝나기 전에 종료됨 | 2-2로 돌아가서 Timeout을 `10 sec`로 변경 |
| `tcp connection failed` 또는 `timed out` | Security Group, subnet, VPC, endpoint 중 하나가 맞지 않음 | 2-5의 VPC와 Security Group 설정 확인 |
| `dns lookup failed` | `DB_HOST` 값이 endpoint가 아니거나 오타가 있음 | RDS의 endpoint만 복사해서 `DB_HOST`에 입력 |

## 3. Lambda가 DB 안으로 로그인할 수 있는지 확인

이번에는 실제 DB username/password로 로그인하고 `SELECT 1`을 실행한다.

확인하는 것:

- DB username/password
- `pymysql` driver
- `SELECT 1`

### 3-1. Lambda 패키지 만들기

로컬 cmd에서 `level3-lambda-rds-connection` 폴더로 이동한다.

```cmd
cd /d "C:\Users\WIN11\KeulKeul\assignment\week4-dynamodb&rds\level3-lambda-rds-connection"
```

`pymysql`을 포함한 zip 파일을 만든다.

```cmd
python -m pip install -r requirements.txt -t package
copy lambda_function.py package\
cd package
tar -a -c -f ..\lambda-rds.zip *
cd ..
```

### 3-2. Lambda 코드 업로드

1. Lambda 함수 화면 → **Code** 탭
2. **Upload from** 클릭
3. **.zip file** 클릭
4. `lambda-rds.zip` 선택
5. zip 업로드 창의 **Update** 클릭
    - 코드 편집기에 직접 붙여넣는 경우에는 **Deploy**를 클릭한다.
6. Runtime settings의 Handler가 아래 값인지 확인

```text
lambda_function.lambda_handler
```

### 3-3. DB 접속 환경 변수 입력

Lambda 함수 화면 → **Configuration** → **Environment variables**에서 아래 값을 입력한다.

```text
DB_HOST=본인 RDS endpoint
DB_PORT=3306
DB_NAME=keulkeul
DB_USER=admin
DB_PASSWORD=직접 설정한 password
```

### 3-4. SELECT 1 테스트

Lambda **Test** 탭에서 새 이벤트를 만든다.

- 이벤트 이름: `select1`
- 붙여넣을 파일: `events/select1.json`

정상 응답 예시:

```json
{
  "statusCode": 200,
  "headers": {
    "Content-Type": "application/json; charset=utf-8"
  },
  "body": "{\"message\": \"select 1 ok\", \"result\": {\"value\": 1}}"
}
```

## 4. Lambda가 vice_president를 찾아오는지 확인

이번에는 `club_members` Table에서 `title`이 `vice_president`인 row를 가져온다.

실제로 실행되는 SQL 형태:

```sql
SELECT *
FROM club_members
WHERE title = 'vice_president';
```

president를 조회하고 싶으면 이벤트의 `title` 값을 `president`로 바꾸면 된다.

### 4-1. Test event 생성

Lambda **Test** 탭에서 새 이벤트를 만든다.

- 이벤트 이름: `find_vice_president`
- 붙여넣을 파일: `events/find_vice_president.json`

`events/find_vice_president.json`

```json
{
  "requestContext": {
    "http": {
      "method": "GET",
      "path": "/"
    }
  },
  "queryStringParameters": {
    "title": "vice_president"
  },
  "isBase64Encoded": false
}
```

정상 응답 예시:

```json
{
  "statusCode": 200,
  "headers": {
    "Content-Type": "application/json; charset=utf-8"
  },
  "body": "{\"message\": \"club members loaded\", \"title\": \"vice_president\", \"count\": 1, \"items\": [{\"id\": 2, \"user_id\": \"yujin\", \"name\": \"Yujin\", \"title\": \"vice_president\", \"status\": \"active\", \"created_at\": \"2026-07-10T15:29:19\", \"updated_at\": null}]}"
}
```

확인할 것:

- `count`가 `1`인가?
- `name`이 `Yujin`인가?
- `title`이 `vice_president`인가?

## 5. 일부러 오류를 내보고 원인 맞히기

아래 실습은 하나씩만 바꿔서 실행한다. 확인이 끝나면 바로 원래 값으로 되돌린다.

| 일부러 바꿀 것 | 만드는 오류 | 예상되는 메시지 |
| --- | --- | --- |
| `DB_PASSWORD`를 틀리게 입력 | DB 로그인 실패 | `Access denied for user` |
| `DB_PORT`를 `3307` 같은 값으로 변경 | 잘못된 port로 접속 | `timed out` 또는 `Connection refused` |
| `keulkeul-rds-sg` source inbound rule 제거 | Lambda가 RDS port에 접근 불가 | `tcp connection failed` 또는 `timed out` |
| `pymysql` 없이 `lambda_function.py`만 붙여넣기 | driver 없음 | `No module named 'pymysql'` |

### 5-1. Wrong password 확인

1. Lambda 함수 → **Configuration** → **Environment variables**
2. `DB_PASSWORD` 값을 일부러 틀리게 변경
3. `select1` 테스트 실행
4. 오류 메시지에서 `Access denied`가 보이는지 확인
5. `DB_PASSWORD`를 원래 값으로 복구

### 5-2. Wrong port 확인

1. `DB_PORT`를 `3307`로 변경
2. `select1` 테스트 실행
3. timeout 또는 connection refused가 보이는지 확인
4. `DB_PORT`를 `3306`으로 복구

### 5-3. Security Group 막힘 확인

1. RDS Security Group으로 이동
2. inbound rule에서 아래 규칙을 잠시 제거
    - Type: `MYSQL/Aurora`
    - Port: `3306`
    - Source: `keulkeul-rds-sg`
3. 네트워크 체크 Lambda를 실행
4. `tcp connection failed`가 보이는지 확인
5. 아래 규칙을 다시 추가
    - Type: `MYSQL/Aurora`
    - Port: `3306`
    - Source: `keulkeul-rds-sg`

### 5-4. Driver 없음 확인

1. Lambda 코드 탭에 `lambda_function.py`만 직접 붙여넣기
2. `pymysql` package가 포함된 zip을 올리지 않은 상태로 테스트 실행
3. `No module named 'pymysql'`가 보이는지 확인
4. 다시 `lambda-rds.zip`을 업로드해서 복구

## 6. 실습 질문

아래 질문에 짧게 답한다.

1. DNS 확인과 TCP connection 확인은 각각 무엇을 확인하는가?
2. `SELECT 1`은 왜 DB 연결 확인에 자주 쓰이는가?
3. `pymysql` driver가 없으면 왜 Lambda에서 import 오류가 나는가?
4. Security Group이 막혔을 때와 password가 틀렸을 때 오류가 어떻게 다른가?
5. DynamoDB보다 RDS 연결에서 확인할 것이 더 많은 이유는 무엇인가?

## 7. 리소스 정리

Level 3까지 끝나면 Week 4에서 만든 AWS 리소스를 정리한다.

### 7-1. Level 3에서 만든 Lambda 리소스 삭제

1. Lambda 함수 삭제
    - `keulkeul-rds-network-check`
2. CloudWatch Log Group 삭제
    - `/aws/lambda/keulkeul-rds-network-check`

### 7-2. Level 2에서 만든 RDS 리소스 삭제

Level 2의 RDS는 Level 3에서 계속 사용했으므로, Level 3까지 끝난 뒤 삭제한다.

1. RDS 콘솔 → **Databases** 이동
2. `keulkeul-rds` 선택
3. **Actions** → **Delete**
4. Final snapshot 생성 여부 선택
5. 안내 문구 입력 후 삭제
6. RDS에서 사용하던 Security Group이 더 이상 필요 없으면 삭제

삭제되는 것:

| 리소스 | 이름 |
| --- | --- |
| RDS DB instance | `keulkeul-rds` |
| RDS database | `keulkeul` |
| RDS table | `club_members` |
| Security Group inbound rule | DB port 허용 규칙 |

### 7-3. Level 1 리소스가 남아 있다면 삭제

Level 1에서 아직 삭제하지 않았다면 아래 리소스도 삭제한다.

| 리소스 | 이름 |
| --- | --- |
| DynamoDB Table | `keulkeul-todos` |
| Lambda 함수 | `keulkeul-dynamodb-api` |
| Function URL | `keulkeul-dynamodb-api`의 Function URL |
| CloudWatch Log Group | `/aws/lambda/keulkeul-dynamodb-api` |

> [!IMPORTANT]
> 삭제 순서는 보통 Function URL → Lambda 함수 → CloudWatch Log Group → DynamoDB/RDS 순서로 하면 헷갈리지 않는다. RDS는 삭제하는 데 몇 분 걸릴 수 있다.
