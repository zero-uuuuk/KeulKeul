## Assignment: RDS 만들고 SQL로 club member role 저장하기

RDS DB instance를 만들고 SQL을 사용해 club member role 데이터를 저장, 조회, 수정, 삭제한다.

참고 자료:
- https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html
- https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ConnectToInstance.html
- https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.RDSSecurityGroups.html

> [!NOTE]
> RDS는 MySQL 같은 관계형 데이터베이스를 AWS에서 관리형으로 제공하는 서비스다. DynamoDB와 달리 SQL, schema, endpoint, port, username/password, security group 개념이 중요하다.

> [!IMPORTANT]
> 이번 실습에서는 RDS를 Public Access로 잠깐 열 수 있다. Security Group에서 DB port를 `0.0.0.0/0`으로 열지 않고, 실습 후 DB instance를 삭제한다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한 (RDS, EC2 Security Group)
- VS Code 확장
  - `Database Client`
- 제공된 SQL 파일
  - `sql/mysql_members.sql`

## 1. RDS DB Instance 생성

AWS Console에서 RDS DB instance를 생성한다.

1. AWS 콘솔 → **RDS** → **Databases**
2. **Create database** 클릭
3. 설정값:
    - 데이터베이스 생성 방식 선택: **전체 구성**
    - 엔진 유형: **MySQL**
    - 템플릿: **샌드박스**
    - 배포 옵션: **단일 AZ DB 인스턴스 배포(인스턴스 1개)**
    - 에디션: **MySQL Community**
    - 엔진 버전: **MySQL 8.4.8**
    - RDS 확장 지원 활성화: 체크 해제
    - DB 인스턴스 식별자: `keulkeul-rds`
    - 마스터 사용자 이름: `admin`
    - 자격 증명 관리: **자체 관리**
    - 암호 자동 생성: 체크 해제
    - 마스터 암호: 직접 설정
    - 데이터베이스 인증 옵션: **암호 인증**
    - DB 인스턴스 클래스: **버스터블 클래스**
    - 인스턴스 유형: `db.t3.micro`
    - 스토리지 유형: **범용 SSD(gp3)**
    - 할당된 스토리지: `20 GiB`
    - 프로비저닝된 IOPS: 기본값 `3000`
    - 스토리지 처리량: 기본값 `125 MiBps`
    - 스토리지 자동 조정 활성화: 체크 해제
    - 컴퓨팅 리소스: **EC2 컴퓨팅 리소스에 연결 안 함**
    - Virtual Private Cloud(VPC): **새 VPC 생성**
    - DB 서브넷 그룹: **새 DB 서브넷 그룹 생성**
    - 퍼블릭 액세스: **예**
    - VPC 보안 그룹(방화벽): **새로 생성**
    - 새 VPC 보안 그룹 이름: `keulkeul-rds-sg`
    - 가용 영역: `ap-northeast-2a`
    - RDS 프록시 생성: 체크 해제
    - 인증 기관: 기본값 그대로 사용
    - 데이터베이스 포트: `3306`
    - Database Insights: **표준**
    - 향상된 모니터링 활성화: 체크 해제
    - 로그 내보내기: 선택하지 않음
    - 초기 데이터베이스 이름: `keulkeul`
    - DB 파라미터 그룹: 기본값 그대로 사용
    - 옵션 그룹: 기본값 그대로 사용
    - 암호화 활성화: 체크 해제
    - 자동 백업 활성화: 체크 해제
    - 마이너 버전 자동 업그레이드 사용: 체크 유지
    - 유지 관리 기간: **기본 설정 없음**
    - 삭제 방지 활성화: 체크 해제
4. **Create database** 클릭

> [!NOTE]
> `초기 데이터베이스 이름`을 비워두면 DB instance는 만들어지지만 `keulkeul` database는 자동 생성되지 않을 수 있다. 가능하면 생성 화면에서 `keulkeul`을 입력한다.

## 2. Security Group 설정

Level 3에서 Lambda가 같은 Security Group으로 RDS에 접근할 수 있도록 Security Group inbound rule을 수정한다.

1. RDS DB instance 화면에서 **Connectivity & security** 탭 확인
2. VPC security group 링크 클릭
3. **Inbound rules** → **Edit inbound rules**
4. 아래 rule 추가

```text
Type: MySQL/Aurora
Port: 3306
Source: keulkeul-rds-sg
```

VS Code Database Client에서 내 PC로 직접 접속해야 하는 경우에는 아래 rule도 추가한다.

```text
Type: MySQL/Aurora
Port: 3306
Source: My IP
```

절대 사용하지 말 것:

```text
Source: 0.0.0.0/0
```

## 3. Endpoint와 Port 확인

RDS DB instance 화면에서 아래 정보를 확인한다.

```text
Endpoint
Port
DB name
Username
Password
```

DB Client 접속에 필요한 정보:

| 항목 | 예시 |
| --- | --- |
| Host | RDS endpoint |
| Port | `3306` |
| Database | `keulkeul` |
| Username | `admin` |
| Password | 직접 설정한 password |

## 4. VS Code Database Client로 접속

VS Code 확장을 사용해 RDS MySQL에 접속한다.

### 4-1. Database Client 확장 설치

1. VS Code 왼쪽 **Extensions** 클릭
2. 검색창에 `mysql` 입력
3. 아래 확장 설치
    - 이름: `MySQL`
    - 게시자: `Database Client`
    - 설명: `Database Management for MySQL/MariaDB...`

> [!IMPORTANT]
> `SQL SERVER` 확장은 Microsoft SQL Server용이다. 이번 실습의 RDS는 MySQL이므로 `SQL SERVER`가 아니라 `Database Client` 게시자의 MySQL 확장을 사용한다.

### 4-2. RDS 연결 생성

1. VS Code 왼쪽의 Database Client 아이콘 클릭
2. **New Connection** 클릭
3. **Server Type**에서 **MySQL** 선택
4. **Main** 탭에서 연결 정보 입력

| 화면 항목 | 입력값 |
| --- | --- |
| Name | `keulkeul-rds` |
| Group | 비워둠 |
| Scope | `Global` |
| Server Type | `MySQL` |
| Host | RDS endpoint |
| Port | `3306` |
| Username | `admin` |
| Password | RDS 생성 때 직접 설정한 master password |
| Database | `keulkeul` |
| Socket Path | 비워둠 |
| Event | 체크 해제 |
| Trigger | 체크 해제 |
| Use Connection String | 꺼둠 |
| SSL | 꺼둠 |

> [!IMPORTANT]
> `Host`의 기본값인 `127.0.0.1`은 내 컴퓨터 자신을 뜻한다. RDS에 접속하려면 반드시 RDS의 endpoint로 바꿔야 한다.

5. **Connect** 클릭
6. 연결 저장이 필요하면 **Save** 클릭

확인할 것:

- Endpoint와 port를 정확히 입력했는가?
- Database name이 `keulkeul`인가?
- Security Group에 `keulkeul-rds-sg` source가 허용되어 있는가?
- VS Code에서 직접 접속한다면 Security Group에서 내 IP가 허용되어 있는가?
- 퍼블릭 액세스가 `예`로 켜져 있는가?

## 5. SQL 실습

아래 SQL 파일을 실행한다.

```text
sql/mysql_members.sql
```

VS Code에서 실행하는 방법:

1. `sql/mysql_members.sql` 파일 열기
2. Database Client에서 `keulkeul-rds` 연결이 선택되어 있는지 확인
3. 위쪽 탭에서 `mysql_members.sql`을 클릭해 SQL 파일을 활성화
4. 각 SQL 구문 위에 보이는 작은 **Run** 클릭
5. 위에서부터 순서대로 실행
    - `DROP TABLE`
    - `CREATE TABLE`
    - `INSERT`
    - `SELECT`
    - `UPDATE`
    - `DELETE`
6. 결과 창에 `SELECT` 결과가 보이는지 확인

> [!NOTE]
> 오른쪽 위의 **Run Code** 버튼은 VS Code의 일반 코드 실행 버튼일 수 있다. 이번 실습에서는 SQL 구문 위에 표시되는 작은 **Run**을 사용한다.

SQL 파일에는 아래 작업이 들어 있다.

1. 기존 `club_members` table 삭제
2. `club_members` table 생성
3. president, vice_president, member 9명 추가
4. 전체 역할 명단 조회
5. `president`, `member` 조건 조회
6. `younguk`의 title을 `president`에서 `member`로 수정
7. `hyunryeo` row 삭제
8. 최종 역할 명단 조회

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

확인할 것:

- SQL에서 schema를 먼저 만들고 row를 넣는 흐름이 보이는가?
- `WHERE title = 'president'` 조건으로 president row만 조회되는가?
- `UPDATE` 후 `younguk`의 title이 `member`로 바뀌는가?
- `DELETE` 후 `hyunryeo` row가 최종 목록에서 사라지는가?

> [!NOTE]
> `Access denied for user 'admin'@'%' to database 'mysql'` 오류가 나오면 `mysql` 시스템 DB에 SQL을 실행한 것이다. 왼쪽 Database Client에서 `keulkeul` DB를 선택하고 다시 실행한다.

## 6. DynamoDB와 비교

이번 실습에서 DynamoDB와 RDS의 차이를 비교한다.

| 구분 | DynamoDB | RDS |
| --- | --- | --- |
| 데이터 단위 | Item | Row |
| 구조 | Table / Item / Attribute | Table / Row / Column |
| 조회 방식 | Key 기반 Query | SQL |
| 연결 방식 | AWS SDK + IAM | Endpoint + Port + 계정 |
| 보안 설정 | IAM 권한 중심 | Security Group + DB 계정 |
| 적합한 경우 | 서버리스 API, key-value 조회 | 관계형 데이터, Join, Transaction |

## 7. 실습 질문

아래 질문에 짧게 답한다.

1. RDS는 NoSQL DB인가, RDB인가?
2. DynamoDB와 달리 RDS에서는 왜 SQL을 사용하는가?
3. RDS Endpoint와 Port는 어떤 역할을 하는가?
4. 퍼블릭 액세스를 켜면 어떤 위험이 있는가?
5. Security Group에서 `0.0.0.0/0`을 열면 왜 위험한가?
6. DynamoDB의 item과 RDS의 row는 어떤 점이 비슷하고 어떤 점이 다른가?
7. `title`처럼 정해진 값만 들어가야 하는 컬럼은 RDS에서 어떻게 제한할 수 있는가?

## 8. 리소스 정리

Level 3에서 같은 RDS DB instance를 계속 사용한다. 따라서 Level 2가 끝났다고 바로 RDS를 삭제하면 안 된다.

| 리소스 | 이름 | 언제 삭제? |
| --- | --- | --- |
| RDS DB instance | `keulkeul-rds` | Level 3까지 끝난 뒤 삭제 |
| RDS database | `keulkeul` | DB instance를 삭제하면 함께 정리됨 |
| RDS table | `club_members` | Level 3에서 사용하므로 유지 |
| Security Group inbound rule | DB port 허용 규칙 | Level 3까지 끝난 뒤 Security Group 삭제 |

Level 2 종료 시점에는 아래만 확인한다.

1. `keulkeul-rds`를 삭제하지 않는다.
2. `club_members` table을 삭제하지 않는다.
3. Security Group inbound rule을 `0.0.0.0/0`로 열어두지 않는다.
4. Public Access를 켰다면 실습 중에만 사용하고, Week 4 전체 종료 후 RDS를 삭제한다.

Level 3까지 모든 실습을 마친 뒤 삭제할 때:

1. RDS 콘솔 → Databases 이동
2. `keulkeul-rds` 선택
3. **Actions** → **Delete**
4. Final snapshot 생성 여부 선택
5. 안내 문구 입력 후 삭제
6. RDS에서 사용하던 Security Group이 더 이상 필요 없으면 삭제
