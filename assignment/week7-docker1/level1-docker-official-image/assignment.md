## Assignment: Docker Official Image를 로컬에서 실행해 보기

Docker Desktop이 설치된 macOS 또는 Windows 환경에서 Docker Hub의 Official Image 여섯 개를 직접 내려받고 실행한다. Linux 환경, 웹 서버, 인메모리 데이터 저장소, 관계형 데이터베이스, 문서형 데이터베이스, Python 런타임을 각각 Container로 다뤄 보며 Docker의 기본 흐름을 익힌다.

참고 자료:

- Docker Desktop 설치: [macOS](https://docs.docker.com/desktop/setup/install/mac-install/), [Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- Docker Hub Official Image: [Alpine](https://hub.docker.com/_/alpine), [Nginx](https://hub.docker.com/_/nginx), [Redis](https://hub.docker.com/_/redis), [PostgreSQL](https://hub.docker.com/_/postgres), [MongoDB](https://hub.docker.com/_/mongo), [Python](https://hub.docker.com/_/python)

## 0. 사전 준비

### 0-1. Docker Desktop 설치 및 실행

1. 사용 중인 운영체제에 맞는 Docker Desktop을 설치한다.
2. Docker Desktop을 실행하고 초기 설정을 완료한다.
3. Docker Desktop이 실행된 상태에서 Terminal 또는 PowerShell을 연다.
4. 아래 명령어를 실행한다.

```bash
docker version
docker image ls
```

> [!NOTE]
> `docker` 명령을 찾을 수 없으면 Docker Desktop 설치 또는 PATH 설정을 확인한다. Client 정보만 보이거나 daemon 연결 오류가 나면 Docker Desktop이 실행 중인지 확인한다.

## 1. Docker Desktop과 Docker Engine 이해하기

### 1-1. macOS와 Windows에서 Linux Container가 실행되는 방법

Docker의 Linux Container는 Linux Kernel이 제공하는 격리 기능을 사용한다. 따라서 Linux에서는 Docker Engine이 Host의 Linux Kernel을 직접 사용할 수 있다.

macOS와 Windows는 Linux Kernel을 사용하지 않으므로 Docker Desktop이 중간에 Linux 실행 환경을 준비한다.

```text
macOS
  ↓
Docker Desktop이 관리하는 Linux VM
  ↓
Docker Engine → Linux Container

Windows
  ↓
Docker Desktop의 WSL 2 backend
  ↓
Linux 환경 → Docker Engine → Linux Container
```

### 1-2. `docker run`의 내부 흐름

`docker run nginx`를 입력하면 Docker CLI가 Docker Engine에 실행 요청을 보내고, 여러 구성 요소가 순서대로 Container 프로세스를 준비한다.

```text
사용자
  ↓ docker run nginx
Docker CLI
  ↓ Docker API
dockerd
  ↓ Container 생명주기 요청
containerd
  ↓ Linux 격리 환경 생성 요청
runc
  ↓ namespace, cgroups 등 Linux Kernel 기능 사용
Nginx Container Process
```

| 구성 요소 | 역할 |
| --- | --- |
| Docker CLI | 사용자가 입력한 `docker` 명령을 Docker Engine에 전달한다. |
| `dockerd` | Image, Container, network, volume 같은 Docker 객체를 관리하는 daemon이다. |
| `containerd` | Container 생성, 시작, 중지 같은 생명주기를 관리한다. |
| `runc` | Linux Kernel의 격리 기능을 설정하고 실제 Container 프로세스를 생성한다. |

> [!NOTE]
> Container는 작은 가상 컴퓨터가 아니라 격리된 Linux 프로세스에 가깝다. VM처럼 Container마다 Guest OS와 Kernel 전체를 새로 실행하지 않으므로 상대적으로 가볍고 빠르게 시작할 수 있다.

### 1-3. 이번 과제의 공통 흐름

```text
Docker Hub
  ↓ docker pull
Local Image Store
  ↓ docker run
Container 생성 및 실행
  ↓ docker ps / docker logs / docker exec
상태 확인 및 Container 내부 작업
  ↓ docker stop / docker rm
Container 정리
```

| 명령어 | 역할 |
| --- | --- |
| `docker pull` | Docker Hub Registry에서 Image를 로컬로 내려받는다. |
| `docker image ls` | 로컬에 저장된 Image 목록을 확인한다. |
| `docker run` | Image를 바탕으로 Container를 생성하고 실행한다. |
| `docker ps` | 현재 실행 중인 Container를 확인한다. |
| `docker logs` | Container의 표준 출력 로그를 확인한다. |
| `docker exec` | 실행 중인 Container 내부에서 추가 명령어를 실행한다. |

> [!IMPORTANT]
> `pull`은 Image를 다운로드하는 작업이고, `run`은 Image를 기반으로 Container를 만들고 실행하는 작업이다.

## 2. Alpine Linux Image 실행

`alpine`은 매우 작은 Linux 배포판인 Alpine Linux를 담은 Official Image다. 이번 단계에서는 Container 내부의 Linux Shell과 파일 시스템을 확인한다.

### 2-1. Alpine Image 내려받기

```bash
docker pull alpine
docker image ls
```

### 2-2. Alpine Container의 Shell 실행

```bash
docker run -it --rm alpine sh
```

| 옵션 | 역할 |
| --- | --- |
| `-i` | 사용자의 표준 입력을 Container에 계속 연결한다. |
| `-t` | 대화형 Terminal 환경을 할당한다. |
| `--rm` | Shell이 종료되면 이번에 생성한 Container를 자동 삭제한다. |
| `sh` | Alpine Container 안에서 실행할 기본 Shell이다. |

Container Shell에서 아래 명령어를 실행한다.

```sh
cat /etc/os-release
pwd
ls
exit
```

## 3. Nginx 웹 서버 Image 실행

`nginx`는 정적 파일을 제공할 수 있는 대표적인 웹 서버 Image다. Container의 80번 포트를 Host의 8080번 포트에 연결하고 브라우저에서 결과를 확인한다.

### 3-1. Nginx Image 내려받기와 Container 실행

```bash
docker pull nginx
docker run -d --name keulkeul-nginx -p 8080:80 nginx
docker ps
```

| 옵션 | 역할 |
| --- | --- |
| `-d` | Container를 백그라운드에서 실행한다. |
| `--name keulkeul-nginx` | 이후 명령어에서 사용할 Container 이름을 지정한다. |
| `-p 8080:80` | Host의 8080 포트 요청을 Container의 80 포트로 전달한다. |

브라우저에서 아래 주소를 연다.

```text
http://localhost:8080
```

### 3-2. 실행 상태와 로그 확인

```bash
docker logs keulkeul-nginx
docker exec keulkeul-nginx nginx -v
```

### 3-3. 기본 `index.html` 바꾸기

Nginx Image의 기본 웹 페이지는 Container 내부의 `/usr/share/nginx/html/index.html`에 있다. Container Shell에 들어가 HTML을 직접 입력해 파일을 바꾼다.

```bash
docker exec -it keulkeul-nginx sh
cat > /usr/share/nginx/html/index.html
```

- `cat > 파일경로`: 이후에 입력하는 내용을 해당 파일에 덮어써서 저장한다.

아래 HTML을 입력한 뒤 `Control+D`를 눌러 파일 입력을 끝낸다.

```html
<h1>Hello from KeulKeul Docker</h1>
```

파일 내용을 확인하고 Container Shell을 종료한다.

```sh
cat /usr/share/nginx/html/index.html
exit
```

브라우저에서 `http://localhost:8080`을 새로고침한다. Nginx를 다시 시작하지 않아도 바뀐 HTML이 바로 표시된다.

> [!NOTE]
> 이번 변경은 `keulkeul-nginx` Container의 writable layer에 저장된다. Container를 삭제하면 이 파일도 함께 사라진다.

## 4. Redis Image 실행

`redis`는 메모리에 데이터를 저장하는 서버다. 외부 포트는 열지 않고, `docker exec`로 Container 내부의 `redis-cli`를 실행해 데이터를 저장하고 조회한다.

### 4-1. Redis Image 내려받기와 Container 실행

```bash
docker pull redis
docker run -d --name keulkeul-redis redis
docker ps
```

### 4-2. Redis CLI로 데이터 저장과 조회

```bash
docker exec -it keulkeul-redis redis-cli
```

Redis CLI에서 아래 명령어를 실행한다.

```text
SET study Docker
GET study
DEL study
GET study
exit
```

> [!IMPORTANT]
> 이번 Redis Container는 로컬 학습용이며 Host 포트를 공개하지 않는다. 실제 서비스에서 Redis 포트를 외부에 공개할 때는 인증과 network 설정을 별도로 고려해야 한다.

## 5. PostgreSQL Image 실행

`postgres`는 SQL을 사용하는 관계형 데이터베이스 서버다. Container를 처음 만들 때 환경 변수로 초기 관리자 비밀번호를 설정하고, `psql`로 SQL을 실행한다.

### 5-1. PostgreSQL Image 내려받기와 Container 실행

```bash
docker pull postgres
docker run -d --name keulkeul-postgres -e POSTGRES_PASSWORD=keulkeul-study postgres
docker logs keulkeul-postgres
```

`POSTGRES_PASSWORD`는 PostgreSQL Image가 최초 데이터베이스를 초기화할 때 필요한 환경 변수다.

로그에 아래와 비슷한 문구가 나올 때까지 기다린다.

```text
database system is ready to accept connections
```

### 5-2. `psql`로 SQL 실행

```bash
docker exec -it keulkeul-postgres psql -U postgres -d postgres
```

- `-U postgres`: PostgreSQL 사용자 이름을 지정한다.
- `-d postgres`: 접속할 데이터베이스 이름을 지정한다.

`psql`에서 아래 SQL을 순서대로 실행한다.

```sql
DROP TABLE IF EXISTS study_notes;
CREATE TABLE study_notes (id SERIAL PRIMARY KEY, title TEXT NOT NULL);
INSERT INTO study_notes (title) VALUES ('Docker Official Image 실습');
SELECT * FROM study_notes;
\q
```

## 6. MongoDB Image 실행

`mongo`는 JSON과 유사한 문서(document) 형태로 데이터를 저장하는 문서형 NoSQL 데이터베이스다. `mongosh`에서 문서를 삽입하고 조회한다.

### 6-1. MongoDB Image 내려받기와 Container 실행

```bash
docker pull mongo
docker run -d --name keulkeul-mongo mongo
docker logs keulkeul-mongo
```

로그에 `Waiting for connections`와 비슷한 문구가 보이면 MongoDB 서버가 요청을 받을 준비가 된 것이다.

### 6-2. `mongosh`로 문서 저장과 조회

```bash
docker exec -it keulkeul-mongo mongosh
```

MongoDB Shell에서 아래 명령어를 순서대로 실행한다.

```javascript
use keulkeul
db.members.deleteMany({})
db.members.insertOne({ name: "KeulKeul", topic: "Docker" })
db.members.find()
exit
```

- `use keulkeul`: `keulkeul` 데이터베이스를 선택한다.
- `db.members.deleteMany({})`: `members` collection에 있는 기존 문서를 모두 삭제한다.
- `db.members.insertOne(...)`: `members` collection에 JSON 형태의 문서 하나를 저장한다.
- `db.members.find()`: `members` collection의 문서를 조회한다.
- `exit`: MongoDB Shell을 종료한다.

## 7. Python 런타임 Image 실행

`python` Image에는 Python 실행 환경이 들어 있다. 장기 실행 서버를 띄우지 않고, Image 안의 Python으로 코드를 한 번 실행한 뒤 Container를 자동 삭제한다.

### 7-1. Python Image 내려받기와 버전 확인

```bash
docker pull python
docker run --rm python python --version
```

### 7-2. Python 코드 실행

```bash
docker run --rm python python -c "import platform; print('Hello from Python container'); print(platform.python_version())"
```

## 8. 전체 Image와 Container 확인

여섯 Image를 모두 사용한 뒤 상태를 확인한다.

```bash
docker image ls
docker ps
docker ps -a
```

## 9. 리소스 정리

이번 과제에서 만든 장기 실행 Container를 중지하고 삭제한다.

```bash
docker stop keulkeul-nginx keulkeul-redis keulkeul-postgres keulkeul-mongo
docker rm keulkeul-nginx keulkeul-redis keulkeul-postgres keulkeul-mongo
docker ps -a
```

이번 과제에서 내려받은 Image도 삭제하려면 아래 명령어를 실행한다.

```bash
docker image rm alpine nginx redis postgres mongo python
docker image ls
```
