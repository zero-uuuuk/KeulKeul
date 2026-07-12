<h1 align="center">Level 3: Lambda + RDS Connection</h1>

<p align="center">
  Lambda가 RDS endpoint를 찾고, port에 연결하고, DB에 로그인하고, SQL을 실행하는 흐름을 단계별로 확인합니다.
</p>

## 파일 구성

```text
.
├── README.md
├── assignment.md
├── lambda_function.py
├── lambda_network_check.py
├── requirements.txt
└── events
    ├── find_vice_president.json
    └── select1.json
```

## 붙여넣을 파일

- `lambda_network_check.py`: 추가 패키지 없이 Lambda 코드에 붙여넣어 DNS와 TCP 연결 확인
- `lambda_function.py`: `pymysql` 패키지와 함께 zip으로 올려 `SELECT 1`과 `club_members` 조회 실행
- `requirements.txt`: `lambda_function.py` 패키징에 필요한 dependency
- `events/select1.json`: DB 로그인과 `SELECT 1` 확인용 Test event
- `events/find_vice_president.json`: `club_members`에서 `vice_president` 조회용 Test event

## 환경 변수

두 Lambda 예제 모두 아래 환경 변수를 사용합니다.

```text
DB_HOST=RDS endpoint
DB_PORT=3306
DB_NAME=keulkeul
DB_USER=admin
DB_PASSWORD=직접 설정한 password
```

`lambda_network_check.py`는 `DB_HOST`, `DB_PORT`만 있어도 동작합니다.

## 빠른 확인 순서

1. Level 2에서 만든 `club_members` Table이 있으면 그대로 사용합니다.
2. 먼저 `lambda_network_check.py`를 붙여넣어 DNS와 TCP 연결을 확인합니다.
3. 연결이 성공하면 `lambda_function.py`와 `requirements.txt`로 zip package를 만들어 업로드합니다.
4. Test event `events/select1.json`으로 DB 로그인과 `SELECT 1` 결과를 확인합니다.
5. Test event `events/find_vice_president.json`으로 `vice_president` row를 조회합니다.
6. password, port, Security Group, driver를 일부러 틀리게 바꿔 오류 원인을 비교합니다.

## 패키징 예시

로컬 터미널에서 `level3-lambda-rds-connection` 폴더로 이동한 뒤 실행합니다.

```cmd
python -m pip install -r requirements.txt -t package
copy lambda_function.py package\
cd package
tar -a -c -f ..\lambda-rds.zip *
cd ..
```

생성된 `lambda-rds.zip`을 Lambda 코드 업로드 화면에 올립니다.
