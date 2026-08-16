## Assignment: Docker Image 만들기

Docker Desktop이 설치된 macOS 또는 Windows 환경에서 Container의 상태를 Image로 저장하고, Dockerfile로 FastAPI 애플리케이션 Image를 만든다. Image와 Container의 관계, 그리고 Image 생성 과정을 익힌다.

## 0. 사전 준비

Docker Desktop을 실행한 뒤 Terminal 또는 PowerShell에서 아래 명령어를 실행한다.

```bash
docker version
docker image ls
```

## 1. Image를 만드는 두 가지 방법

Image를 바탕으로 Container를 만들 수 있다. Container에 프로그램을 설치하거나 파일을 변경한 뒤, 그 상태를 새로운 Image로 저장할 수도 있다.

```text
Official Image
  ↓ docker run
Container
  ↓ 프로그램 설치 또는 파일 변경
변경된 Container
  ↓ docker commit
새로운 Image
```

`docker commit`으로 만든 Image에는 Container의 파일 시스템 변경 상태와 설정이 저장된다. 실행 중인 프로세스와 Volume에 mount한 데이터는 Image에 포함되지 않는다.

Image를 반복해서 만들고 공유할 때는 Dockerfile을 사용한다.

```text
Dockerfile + 애플리케이션 파일
  ↓ docker build
Image
  ↓ docker run
Container
```

Dockerfile은 Image를 만드는 과정을 순서대로 기록한 파일이다. 실제 개발에서는 동일한 환경을 다시 만들고 다른 사람과 공유해야 하므로 Dockerfile 방식이 주로 사용된다.

## 2. Container 상태를 Image로 저장하기

### 2-1. Ubuntu Image 내려받기와 Container 실행

```bash
docker pull ubuntu:24.04
docker run -it --name keulkeul-ubuntu ubuntu:24.04 bash
```

- `-it`: Container의 Shell에 입력하고 결과를 볼 수 있는 Terminal을 연다.
- `--name keulkeul-ubuntu`: 이후 명령에서 사용할 Container 이름을 지정한다.
- `bash`: Ubuntu Container 안에서 실행할 Shell이다.

### 2-2. Container 안에 Git 설치

Container Shell에서 아래 명령어를 실행한다.

```bash
apt update && apt install -y git
git --version
exit
```

`exit`을 입력하면 `keulkeul-ubuntu` Container가 멈춘다. 멈춘 Container의 상태도 Image로 저장할 수 있다.

### 2-3. 변경된 Container를 Image로 저장

```bash
docker commit keulkeul-ubuntu keulkeul-ubuntu-git:1.0
docker image ls
```

```text
docker commit [Container 이름] [Image 이름:Tag]
```

`keulkeul-ubuntu-git:1.0`은 Ubuntu에 Git이 설치된 상태를 담은 새 Image다.

### 2-4. 새 Image에서 Git 실행

```bash
docker run --rm keulkeul-ubuntu-git:1.0 git --version
```

새 Container를 만들었지만 Git 설치 명령을 다시 실행하지 않아도 된다. Git이 포함된 Image를 기반으로 시작했기 때문이다.

## 3. Dockerfile로 FastAPI Image 만들기

`server` 폴더에는 간단한 FastAPI 앱과 의존성 목록이 들어 있다. 이 폴더에 Dockerfile을 만들고, FastAPI 앱을 실행하는 Image를 build한다.

```text
server/
├── main.py
├── requirements.txt
└── Dockerfile             ← 직접 작성
```

### 3-1. 실습 폴더로 이동

Terminal 또는 PowerShell에서 이 과제의 `server` 폴더로 이동한다.

```bash
cd server
```

`main.py`에는 `/` 요청에 JSON 메시지를 반환하는 FastAPI 앱이 들어 있다. `requirements.txt`에는 Image를 만들 때 설치할 FastAPI와 Uvicorn이 적혀 있다.

### 3-2. Dockerfile 작성

`server` 폴더에 확장자 없이 이름이 `Dockerfile`인 파일을 만들고 아래 내용을 입력한다.

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

| 명령어 | 역할 |
| --- | --- |
| `FROM python:3.13-slim` | Python이 설치된 Official Image를 Base Image로 지정한다. |
| `WORKDIR /app` | 이후 명령어의 작업 Directory를 `/app`으로 지정한다. |
| `COPY requirements.txt .` | Host의 의존성 목록을 Image의 `/app`으로 복사한다. |
| `RUN ...` | Image build 과정에서 FastAPI와 Uvicorn을 설치한다. |
| `COPY main.py .` | Host의 FastAPI 소스 코드를 Image의 `/app`으로 복사한다. |
| `CMD [...]` | Container가 시작될 때 Uvicorn으로 FastAPI 앱을 실행한다. |

`RUN`은 `docker build` 중에 실행되고, `CMD`는 `docker run`으로 Container가 시작될 때 실행된다.

### 3-3. FastAPI Image build

```bash
docker build -t keulkeul-fastapi:1.0 .
docker image ls
docker image history keulkeul-fastapi:1.0
```

> [!NOTE]
> `docker image history`는 Image를 구성하는 layer의 생성 명령과 크기를 보여 준다. Dockerfile의 `FROM`, `RUN`, `COPY` 같은 단계가 layer로 쌓인다.

```text
docker build -t [Image 이름:Tag] [Build Context]
```

- `-t keulkeul-fastapi:1.0`: 생성할 Image의 이름과 Tag를 지정한다.
- 마지막 `.`: 현재 `server` 폴더를 Build Context로 전달한다.

Build Context 안에 `main.py`와 `requirements.txt`가 있으므로 Dockerfile의 `COPY` 명령어가 두 파일을 Image 안으로 복사할 수 있다.

### 3-4. FastAPI Container 실행

```bash
docker run -d --name keulkeul-fastapi -p 8000:8000 keulkeul-fastapi:1.0
docker ps
docker logs keulkeul-fastapi
```

- `-d`: Container를 백그라운드에서 실행한다.
- `-p 8000:8000`: Host의 8000 포트 요청을 Container의 8000 포트로 전달한다.

브라우저에서 아래 주소를 연다.

```text
http://localhost:8000
http://localhost:8000/docs
```

`/`에서는 JSON 메시지가 표시되고, `/docs`에서는 FastAPI가 생성한 API 문서를 볼 수 있다.

## 4. 소스 코드를 바꾸고 새 Image 만들기

`main.py`의 메시지를 원하는 문장으로 수정한다.

```python
return {"message": "Docker Image version 1.1"}
```

수정한 소스를 포함하도록 새 Tag로 Image를 다시 build한다.

```bash
docker build -t keulkeul-fastapi:1.1 .
docker rm -f keulkeul-fastapi
docker run -d --name keulkeul-fastapi -p 8000:8000 keulkeul-fastapi:1.1
```

브라우저에서 `http://localhost:8000`을 새로고침한다. 변경한 메시지가 표시된다.

```text
main.py 수정
  ↓ docker build
keulkeul-fastapi:1.1 Image
  ↓ docker run
새 Container
```

Image는 build 시점의 파일을 담는다. Host에서 `main.py`를 수정해도 이미 실행 중인 `keulkeul-fastapi:1.0` Container의 내용은 바뀌지 않는다. 수정 내용을 반영하려면 새 Image를 build하고 그 Image로 Container를 실행해야 한다.

## 5. 리소스 정리

이번 과제에서 만든 Container를 삭제한다.

```bash
docker rm -f keulkeul-ubuntu keulkeul-fastapi
docker ps -a
```

이번 과제에서 만든 Image와 사용한 Base Image를 삭제하려면 아래 명령어를 실행한다.

```bash
docker image rm keulkeul-ubuntu-git:1.0 keulkeul-fastapi:1.0 keulkeul-fastapi:1.1 ubuntu:24.04 python:3.13-slim
docker image ls
```
