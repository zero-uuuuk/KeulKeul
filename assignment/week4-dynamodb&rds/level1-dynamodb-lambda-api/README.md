<h1 align="center">Level 1: DynamoDB Table + Lambda API</h1>

<p align="center">
  DynamoDB Table을 만들고, Lambda Test event로 club member role 데이터를 생성/조회/수정/삭제합니다.
</p>

## 파일 구성

```text
.
├── README.md
├── assignment.md
├── iam-policy-dynamodb-todos.json
├── lambda_function.py
└── events
    ├── delete_member_hyunryeo.json
    ├── list_president.json
    ├── seed_members.json
    └── update_president_to_member.json
```

## 붙여넣을 파일

- `lambda_function.py`: Lambda 코드 탭에 그대로 붙여넣기
- `events/*.json`: Lambda Test event에 붙여넣기
- `iam-policy-dynamodb-todos.json`: 최소 권한 inline policy 예시

## DynamoDB Table 설정

```text
Table name: keulkeul-todos
Partition key: user_id
Partition key type: String
Sort key: todo_id
Sort key type: String
Capacity mode: On-demand
```

item은 직접 입력하지 않고 `events/seed_members.json`으로 생성합니다.

## 이벤트 시나리오

| Event | 역할 |
| --- | --- |
| `seed_members.json` | president, vice_president, member 9명을 한 번에 생성 |
| `list_president.json` | `title = president` item 조회 |
| `update_president_to_member.json` | `younguk`의 title을 `president`에서 `member`로 변경 |
| `delete_member_hyunryeo.json` | `hyunryeo` member item 삭제 |

## API 동작

| Method | 역할 |
| --- | --- |
| `GET` | `title` 또는 `user_id`의 역할 item 조회 |
| `POST` | club member 역할 item 생성 |
| `PATCH` / `PUT` | 역할 title, status, name 수정 |
| `DELETE` | 역할 item 삭제 |

## 환경 변수

Lambda 환경 변수는 선택 사항입니다.

```text
TABLE_NAME=keulkeul-todos
```

환경 변수를 만들지 않으면 코드가 기본값 `keulkeul-todos`를 사용합니다.
