<h1 align="center">Week 4: DynamoDB & RDS 실습</h1>

<p align="center">
  AWS의 대표 Database 서비스인 <code>DynamoDB</code>와 <code>RDS</code>를 실습 예제로 비교합니다.<br>
  콘솔에 붙여넣을 JSON, Lambda 코드, SQL 파일을 레벨별로 분리해 두었습니다.
</p>

## 파일 구성

```text
.
├── README.md
├── level1-dynamodb-lambda-api
│   ├── README.md
│   ├── assignment.md
│   ├── iam-policy-dynamodb-todos.json
│   ├── lambda_function.py
│   └── events
│       ├── delete_member_hyunryeo.json
│       ├── list_president.json
│       ├── seed_members.json
│       └── update_president_to_member.json
├── level2-rds-sql
│   ├── README.md
│   ├── assignment.md
│   └── sql
│       └── mysql_members.sql
├── level3-lambda-rds-connection
│   ├── README.md
│   ├── assignment.md
│   ├── lambda_function.py
│   ├── lambda_network_check.py
│   ├── requirements.txt
│   └── events
│       ├── find_vice_president.json
│       └── select1.json
```

## 전체 흐름

| Level | 주제 | 목표 |
| --- | --- | --- |
| Level 1 | DynamoDB Table + Lambda 동아리 역할 API 만들기 | Table 생성 후 Lambda Test event로 생성/조회/수정/삭제 |
| Level 2 | RDS 만들고 SQL로 동아리 역할 명단 저장하기 | 관계형 DB와 SQL CRUD 실습 |
| Level 3 | Lambda에서 RDS 연결 단계별 확인하기 | DNS, TCP connection, DB 로그인, SQL 실행, 오류 원인 비교 |

## 실습 리소스 이름

실습 문서에서는 아래 이름을 기준으로 설명합니다. 이미 같은 이름을 사용 중이면 본인 이름이나 날짜를 뒤에 붙여도 됩니다.

```text
DynamoDB table: keulkeul-todos
DynamoDB Lambda: keulkeul-dynamodb-api
RDS DB instance: keulkeul-rds
RDS database name: keulkeul
RDS table name: club_members
```

## 주의

- 실습용 리소스는 비용이 발생할 수 있으므로 마지막에 반드시 삭제합니다.
- Function URL을 `Auth type: NONE`으로 열면 URL을 아는 사람이 누구나 호출할 수 있습니다.
- RDS를 Public Access로 열 경우 Security Group source는 반드시 `My IP`만 허용합니다.
- Security Group에서 DB port를 `0.0.0.0/0`으로 열지 않습니다.
- DynamoDB 데이터는 Lambda Test event로 생성합니다.
