## Assignment: Docker Compose로 Web + FastAPI + MySQL 연결하기

React + Vite Web, FastAPI API, MySQL Database를 각각 Container로 실행하고 Docker Compose로 하나의 환경에 연결한다. `docker run`으로 여러 Container를 직접 실행하는 과정을 확인한 뒤, `compose.yaml`로 여러 Service의 실행 설정을 관리하는 방법을 익힌다.

Web에서 Todo 목록 조회·생성·수정·삭제를 수행하고, FastAPI가 Compose Network 안의 `db` Service를 통해 MySQL에 연결하는 흐름을 확인한다.

Web·FastAPI 소스 코드, Dockerfile, MySQL 초기화 SQL, 완성된 `compose.yaml`은 제공된 파일을 사용한다.

## 0. 사전 준비

Docker Desktop을 실행한 뒤 Terminal에서 아래 명령어를 실행한다.

```bash
docker version
docker compose version
```

이 과제의 실습 폴더로 이동한다.

```bash
cd assignment/week8-docker2/level2-docker-compose
```

## 1. `docker run`으로 세 Container 직접 실행하기

Docker Compose의 필요성을 확인하기 위해 먼저 `docker run`으로 같은 환경을 구성한다.

### 1-1. Image 준비

API와 Web Image를 직접 Build한다. MySQL Official Image를 내려받는다.

```bash
docker build -t week8-level2-api:run ./api
docker build -t week8-level2-web:run ./web
docker pull mysql:8.4
```

### 1-2. Network와 Volume 생성

세 Container가 Service 이름으로 통신할 수 있도록 User-defined Network를 생성한다. MySQL 데이터 저장용 Volume도 생성한다.

```bash
docker network create week8-level2-network
docker volume create week8-level2-mysql-data
```

> [!NOTE]
> Compose Network에서는 같은 프로젝트의 Service가 Service 이름을 Hostname으로 사용해 통신한다. 이 단계에서는 `--network-alias db`, `--network-alias api`가 Compose Service 이름과 같은 역할을 한다.

### 1-3. `db` Container 실행

실행 순서의 첫 번째 Service인 MySQL을 실행한다. `--network-alias db`로 Network 안에서 `db`라는 이름을 사용할 수 있다.

```bash
docker run -d \
  --name week8-level2-db \
  --network week8-level2-network \
  --network-alias db \
  -e MYSQL_ROOT_PASSWORD=rootpassword \
  -e MYSQL_DATABASE=keulkeul \
  -e MYSQL_USER=keulkeul_user \
  -e MYSQL_PASSWORD=keulkeul_password \
  -v week8-level2-mysql-data:/var/lib/mysql \
  -v "$PWD/db/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro" \
  mysql:8.4
```

MySQL 초기화가 끝날 때까지 로그를 확인한다.

```bash
docker logs -f week8-level2-db
```

`ready for connections` 문구가 표시되면 `Ctrl + C`로 로그 확인을 종료한다.

### 1-4. `api` Container 실행

두 번째 Service인 FastAPI를 실행한다. API Image에는 MySQL 접속 정보를 환경변수로 전달한다.

`--network-alias api`는 Web의 Vite Proxy가 사용하는 주소를 제공한다.

```bash
docker run -d \
  --name week8-level2-api \
  --network week8-level2-network \
  --network-alias api \
  -p 8000:8000 \
  -e DB_HOST=db \
  -e DB_PORT=3306 \
  -e DB_NAME=keulkeul \
  -e DB_USER=keulkeul_user \
  -e DB_PASSWORD=keulkeul_password \
  week8-level2-api:run
```

### 1-5. `web` Container 실행

세 번째 Service인 Web을 실행한다.

```bash
docker run -d \
  --name week8-level2-web \
  --network week8-level2-network \
  -p 5173:5173 \
  week8-level2-web:run
```

실행 중인 Container를 확인한다.

```bash
docker ps
```

### 1-6. 직접 실행 환경 정리

Docker Compose 실습을 시작하기 전에 `docker run`으로 생성한 Container와 Network를 제거한다. Compose 실습과 구분하기 위해 직접 실행 환경에서 생성한 Volume도 제거한다.

```bash
docker rm -f week8-level2-web week8-level2-api week8-level2-db
docker network rm week8-level2-network
docker volume rm week8-level2-mysql-data
```

## 2. 여러 Container를 Compose로 관리하는 이유

`docker run`으로 세 Container를 실행하려면 Image, Network, Port, Environment Variable, Volume, Network Alias를 여러 명령어에 나누어 작성해야 한다.

실행 순서도 직접 관리해야 한다.

```text
db Container 시작
      ↓
api Container 시작
      ↓
web Container 시작
```

Docker Compose는 여러 Container의 실행 설정을 하나의 YAML 파일에 선언한다. 이후 아래 명령어 하나로 동일한 환경을 실행할 수 있다.

```bash
docker compose up --build -d
```

| 구성 요소 | 역할 |
| --- | --- |
| `db` Service | Todo 데이터 저장 |
| `api` Service | Todo CRUD API 제공 |
| `web` Service | React + Vite 화면 제공 |
| Compose Network | Service 이름 기반 내부 통신 |
| Named Volume | MySQL 데이터 보존 |
| `compose.yaml` | 여러 Service의 실행 설정 선언 |

## 3. Web + FastAPI + MySQL 구조

이번 과제에서는 `db`, `api`, `web` 세 Service를 사용한다.

실행 순서는 `db → api → web`이다. `api`는 `db`에 의존하고, `web`은 `api`에 의존한다.

```text
db Service
  MySQL 8.4
  db:3306
      ↑
api Service
  FastAPI + PyMySQL
  localhost:8000
      ↑
web Service
  React + Vite
  localhost:5173
```

Browser 요청의 흐름은 다음과 같다.

```text
Browser → localhost:5173 → Web
Web → api:8000          → FastAPI
FastAPI → db:3306       → MySQL
```

### 3-1. Host Port와 Container Port

Browser는 Host Port를 통해 Web과 FastAPI에 접근한다.

| 접속 주소 | 연결 대상 |
| --- | --- |
| `http://localhost:5173` | Web Container의 Vite Port 5173 |
| `http://localhost:8000` | FastAPI Container의 Port 8000 |
| `http://localhost:8000/docs` | FastAPI Swagger UI |

MySQL은 Host Port를 공개하지 않는다. FastAPI가 Compose Network 안에서 `db:3306`으로 MySQL에 접속한다.

### 3-2. Service 이름으로 통신하기

Compose Network 안에서는 Service 이름을 Hostname으로 사용해 통신한다.

| 통신 주체 | 주소 | 의미 |
| --- | --- | --- |
| Web → FastAPI | `api:8000` | `api` Service의 Port 8000 |
| FastAPI → MySQL | `db:3306` | `db` Service의 Port 3306 |
| Browser → Web | `localhost:5173` | Host에 공개한 Web Port |
| Browser → FastAPI | `localhost:8000` | Host에 공개한 API Port |

> [!IMPORTANT]
> FastAPI의 MySQL Host는 Compose Service 이름인 `db`다. `localhost`는 FastAPI Container 자신을 가리키므로 MySQL 연결 주소로 사용할 수 없다.

## 4. 제공 파일 확인

현재 폴더의 구조를 확인한다.

```text
level2-docker-compose/
├── assignment.md
├── compose.yaml
├── db/
│   └── init.sql
├── api/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
└── web/
    ├── Dockerfile
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        └── styles.css
```

| 경로 | 역할 |
| --- | --- |
| `db/init.sql` | MySQL Database와 `todos` Table 초기화 |
| `api/` | FastAPI Todo API와 Dockerfile 제공 |
| `web/` | React + Vite Web과 Dockerfile 제공 |
| `compose.yaml` | 세 Service의 실행 설정 제공 |

Web은 `/api` 경로로 FastAPI를 호출한다. `web/vite.config.js`의 Proxy가 Compose Network 안의 `api:8000`으로 요청을 전달한다.

FastAPI는 PyMySQL로 MySQL에 연결한다. `api/main.py`에는 MySQL 초기화 지연에 대응하는 연결 재시도 로직이 포함되어 있다.

## 5. `compose.yaml` 확인

다음 설정을 읽고 각 항목의 역할을 확인한다.

```yaml
services:
  db:
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: keulkeul
      MYSQL_USER: keulkeul_user
      MYSQL_PASSWORD: keulkeul_password
    volumes:
      - mysql_data:/var/lib/mysql
      - ./db/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro

  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      DB_HOST: db
      DB_PORT: 3306
      DB_NAME: keulkeul
      DB_USER: keulkeul_user
      DB_PASSWORD: keulkeul_password
    depends_on:
      - db

  web:
    build: ./web
    ports:
      - "5173:5173"
    depends_on:
      - api

volumes:
  mysql_data:
```

YAML 설정만으로 의미를 파악하기 어려운 항목만 아래 표로 정리한다.

### 5-1. `db` Service에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| MySQL Container Port | `3306` | Compose Network 안의 MySQL 접속 Port |
| 데이터 Volume | `mysql_data` | Container 삭제 이후에도 유지되는 MySQL 저장소 |
| 초기화 SQL | `./db/init.sql` | 빈 Volume 최초 생성 시 실행하는 SQL 파일 |

### 5-2. `api` Service에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| `DB_HOST` | `db` | Compose Network 안의 MySQL Service 이름 |
| 의존 Service | `db` | `db` 시작 이후 `api` 시작 관계 |

`web` Service는 `./web` Build Context, `5173:5173` Port, `api` 의존 관계를 사용한다. Host Port와 Container Port의 연결은 앞서 확인한 구조와 같다.

## 6. `db → api → web` 순서로 실행하기

세 Service를 Build하고 Background에서 실행한다.

```bash
docker compose up --build -d
```

`depends_on` 설정에 따라 `db`, `api`, `web` Container가 순서대로 시작된다.

실행 상태를 확인한다.

```bash
docker compose ps
```

다음과 비슷하게 세 Service가 표시되는지 확인한다.

```text
NAME                         SERVICE   STATUS
level2-docker-compose-db-1   db        running
level2-docker-compose-api-1  api       running
level2-docker-compose-web-1  web       running
```

전체 로그를 확인한다.

```bash
docker compose logs
```

MySQL 로그를 확인한다.

```bash
docker compose logs db
```

`ready for connections` 문구가 표시되면 MySQL이 SQL 요청을 처리할 준비가 된 상태다.

FastAPI는 MySQL 연결을 최대 10회, 2초 간격으로 재시도한다.

## 7. Web과 FastAPI 확인

Browser에서 아래 주소를 열고, 정상적으로 작동하는지 확인한다.

```text
http://localhost:5173
http://localhost:8000/docs
```

`http://localhost:5173`을 새로고침한 뒤 다음 작업을 수행한다.

1. 입력창에 Todo 제목을 입력하고 추가한다.
2. Checkbox를 선택해 완료 상태를 바꾼다.
3. 수정 버튼을 눌러 제목을 변경한다.
4. 삭제 버튼을 눌러 Todo를 삭제한다.
5. 새로고침 후 변경된 목록을 확인한다.

## 8. Named Volume으로 데이터 보존 확인

Web에서 새로운 Todo를 하나 추가한다.

```text
Compose Volume Test
```

현재 실행 중인 Container를 종료하고 제거한다.

```bash
docker compose down
```

`mysql_data` Volume은 유지된다. 다시 Service를 실행한다.

```bash
docker compose up -d
```

`http://localhost:5173`에서 `Compose Volume Test` Todo가 남아 있는지 확인한다.

`init.sql`은 빈 Volume이 처음 생성될 때 실행된다. 기존 `mysql_data` Volume을 사용하는 재실행에서는 초기화 SQL이 다시 실행되지 않는다.

## 9. Compose 종료와 리소스 정리

Compose가 생성한 Container와 기본 Network를 제거한다.

```bash
docker compose down
docker compose ps -a
```

Named Volume까지 제거하면 MySQL 데이터와 초기화 상태가 삭제된다.

```bash
docker compose down -v
docker compose ps -a
docker volume ls
```

> [!IMPORTANT]
> `docker compose down`은 `mysql_data` Volume을 유지한다. `docker compose down -v`는 Volume까지 삭제하므로 다음 실행에서 `db/init.sql`이 다시 실행된다.

## 10. 최종 확인

아래 항목을 순서대로 확인한다.

- `docker compose config`가 오류 없이 실행되는지 확인
- `db`, `api`, `web` 세 Service가 실행되는지 확인
- `http://localhost:5173`에서 Web 화면이 표시되는지 확인
- `http://localhost:8000/docs`에서 FastAPI 문서가 표시되는지 확인
- Todo 생성·조회·수정·완료 처리·삭제가 동작하는지 확인
- FastAPI가 `db:3306`으로 MySQL에 연결하는지 확인
- `docker compose down` 후 Todo 데이터가 유지되는지 확인
- `docker compose down -v` 후 초기 Todo 데이터로 돌아가는지 확인

최종적으로 다음 구조를 이해하면 된다.

```text
compose.yaml
│
├── db Service
│   └── MySQL + mysql_data Volume
│
├── api Service
│   └── FastAPI + PyMySQL
│
└── web Service
    └── React + Vite
```
