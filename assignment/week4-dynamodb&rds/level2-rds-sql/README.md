<h1 align="center">Level 2: RDS SQL Club Member Roles</h1>

<p align="center">
  RDS MySQL DB instance를 만들고 SQL로 club member role 데이터를 추가, 조회, 수정, 삭제합니다.
</p>

## 파일 구성

```text
.
├── README.md
├── assignment.md
└── sql
    └── mysql_members.sql
```

## 사용할 파일

- SQL 파일: `sql/mysql_members.sql`
- DB Client: VS Code `Database Client` 확장

`mysql_members.sql` 파일을 VS Code에서 열고, Database Client의 `keulkeul-rds` 연결을 선택한 뒤 SQL 구문 위의 작은 **Run**을 순서대로 실행합니다.

SQL 파일은 아래 흐름으로 구성되어 있습니다.

1. `club_members` table 삭제 후 생성
2. president, vice_president, member 9명 seed
3. 전체 조회
4. `president`, `member` 조건 조회
5. `younguk`의 title을 `president`에서 `member`로 변경
6. `hyunryeo` row 삭제
7. 최종 목록 조회

## 실습값

```text
DB instance identifier: keulkeul-rds
Database name: keulkeul
Master username: admin
MySQL port: 3306
Table name: club_members
```
