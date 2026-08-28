## Assignment: Docker Image를 GitHub Container Registry에 올리기

Docker Image를 내 Computer의 Local Docker에서 GitHub Container Registry(GHCR)로 업로드한다. Image 이름에 Registry 주소와 GitHub Namespace를 포함하고, GitHub PAT로 인증한 뒤 `push`와 `pull`을 수행하며 원격 Registry를 통한 Image 공유 흐름을 익힌다.

이번 과제는 Registry에 Docker Image를 공유하는 과정을 중심으로 진행하며, 실습용 Local Image는 Docker Hub Official Image인 `ubuntu:24.04`를 사용한다.

참고 자료:

- GitHub Docs: [Working with the Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- Docker Docs: [docker image tag](https://docs.docker.com/reference/cli/docker/image/tag/)

## 0. 사전 준비

Docker Desktop을 실행한 뒤 Terminal 또는 PowerShell에서 아래 명령어를 실행한다.

```bash
docker version
docker image ls
```

## 1. Docker Image를 외부에 공유하기 — Registry

지금까지 사용한 Image는 기본적으로 내 Computer의 Local Docker에만 존재한다. 다른 Computer나 다른 사람이 같은 Image를 사용하려면 원격 저장소에 Image를 업로드해야 한다.

Docker에서 Docker Image를 저장하고 공유하는 원격 저장소를 `Registry`라고 한다.

```text
Dockerfile / Container
        ↓ docker build / docker commit
      Local Image
        ↓ docker push
      Registry
        ↓ docker pull
     다른 Computer
        ↓ docker run
      Container
```

| 구성 요소 | 역할 |
| --- | --- |
| Local Image | 현재 Computer의 Docker에 저장된 Image |
| Registry | Docker Image를 저장하고 공유하는 원격 저장소 |
| Tag | 같은 Image의 버전이나 용도를 구분하는 이름 |
| `docker push` | Local Image를 Registry에 업로드 |
| `docker pull` | Registry의 Image를 Local Docker로 내려받기 |

## 2. GitHub Container Registry 이해하기

GitHub Container Registry는 GitHub Packages에서 Docker와 OCI Image를 저장하는 Registry다. Registry 주소는 `ghcr.io`이며, Image 이름에 Registry 주소와 GitHub Namespace를 함께 적는다.

```text
ghcr.io/[GitHub 사용자명]/[Image 이름]:[Tag]
```

예를 들어 GitHub 사용자명이 `my-user`이고 Image 이름이 `keulkeul-ubuntu-git`이라면 GHCR용 Image 이름은 다음과 같다.

```text
ghcr.io/my-user/keulkeul-ubuntu-git:1.0
```

| 부분 | 의미 |
| --- | --- |
| `ghcr.io` | GitHub Container Registry 주소 |
| `my-user` | GitHub 사용자 또는 Organization Namespace |
| `keulkeul-ubuntu-git` | GitHub Packages에 생성될 Container Package 이름 |
| `1.0` | 업로드할 Image의 Tag |

> [!IMPORTANT]
> GHCR용 Image 이름은 GitHub 사용자명과 Image 이름을 포함해야 한다. `keulkeul-ubuntu-git:1.0`처럼 Local 이름만 사용하는 Image는 GHCR에 바로 Push할 수 없다.

## 3. GitHub PAT 준비하기

Terminal에서 GHCR에 Image를 Push하려면 GitHub 인증이 필요하다. GitHub Settings에서 Personal Access Token (classic)을 만들고 Package에 필요한 권한을 선택한다.

### 3-1. Personal Access Token (classic) 만들기

1. GitHub의 [Personal access tokens](https://github.com/settings/tokens) 페이지를 연다.
2. `Tokens (classic)`으로 이동하고 `Generate new token (classic)`을 선택한다.
3. Token의 만료 기간을 학습에 필요한 범위로 지정한다.
4. Package에 필요한 `read:packages`, `write:packages`, `delete:packages` 권한을 선택한다.
5. Token을 생성하고 다시 표시되지 않으므로 안전한 곳에 한 번만 복사해 둔다.

| 권한 | 역할 |
| --- | --- |
| `read:packages` | Package와 Image를 내려받는다. |
| `write:packages` | Package와 Image를 업로드하고 Metadata를 수정한다. |
| `delete:packages` | Package를 삭제한다. |

### 3-2. GHCR 로그인

아래 명령어를 실행한다.

```bash
docker login ghcr.io
```

질문에 다음 값을 입력한다.

| 질문 | 입력할 값 |
| --- | --- |
| Username | GitHub 사용자명 |
| Password | 생성한 PAT |

로그인에 성공하면 아래와 비슷한 문구가 표시된다.

```text
Login Succeeded
```

## 4. Local Image 준비 및 Commit하기

`ubuntu:24.04` Image를 내려받고 Container 안에 Git을 설치한다.

### 4-1. Ubuntu Image 내려받기와 Container 실행

```bash
docker pull ubuntu:24.04
docker run -it --name keulkeul-ubuntu ubuntu:24.04 bash
```

- `-it`: Container의 Shell에 입력하고 결과를 볼 수 있는 Terminal을 연다.
- `--name keulkeul-ubuntu`: 이후 명령에서 사용할 Container 이름을 지정한다.
- `bash`: Ubuntu Container 안에서 실행할 Shell이다.

### 4-2. Container 안에 Git 설치

Container Shell에서 아래 명령어를 실행한다.

```bash
apt update && apt install -y git
git --version
exit
```

`exit`을 입력하면 `keulkeul-ubuntu` Container가 멈춘다. 멈춘 Container의 상태를 Image로 저장한다.

### 4-3. 변경된 Container를 Image로 저장

```bash
docker commit keulkeul-ubuntu keulkeul-ubuntu-git:1.0
docker image ls
```

`docker commit`은 Container의 파일 시스템 변경 상태를 새로운 Image로 저장한다.

## 5. GHCR용 Image Tag 추가하기

Local Image에 Registry 주소와 GitHub Namespace가 포함된 Tag를 추가한다. 아래 명령어의 `USERNAME`은 자신의 GitHub 사용자명으로 바꾼다.

> [!NOTE]
> Image 이름과 Namespace는 소문자로 작성한다. GitHub 사용자명에 대문자가 포함되어 있으면 GHCR용 Image 이름에서는 소문자로 바꿔 입력한다.

```bash
docker tag keulkeul-ubuntu-git:1.0 ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0
docker image ls
```

Image 목록에 GHCR용 Tag가 보이면 성공이다.

```text
ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0
```

`docker tag`는 같은 Image를 가리키는 GHCR용 이름을 추가한다.

| 명령어 | 역할 |
| --- | --- |
| `docker tag` | 기존 Image에 새로운 이름과 Tag 추가 |
| `ghcr.io` | Push 대상인 GitHub Container Registry 지정 |
| `USERNAME` | Image를 소유할 GitHub 사용자 또는 Organization |
| `keulkeul-ubuntu-git:1.0` | GitHub Packages에 저장할 Image 이름과 버전 |

## 6. GHCR에 Docker Image Push하기

GHCR용 Tag가 붙은 Image를 GitHub Container Registry에 업로드한다.

```bash
docker push ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0
```

Image는 여러 Layer로 구성되어 있으므로 Push할 때 Layer 단위로 업로드된다. 이미 Registry에 존재하는 Layer는 다시 업로드하지 않을 수 있다.

```text
ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0
             ↓ docker push
GitHub Container Registry
             ↓
GitHub Packages의 Container Package
```

Push가 완료되면 GitHub에서 Package를 확인한다.

1. GitHub에서 자신의 Profile을 연다.
2. `Packages` 영역으로 이동한다.
3. `keulkeul-ubuntu-git` Container Package를 연다.
4. Package 이름과 `1.0` Tag가 표시되는지 확인한다.

> [!NOTE]
> 명령어로 처음 Push한 Container Package는 기본적으로 Private으로 생성될 수 있다. 다른 사람이 인증 없이 Pull해야 한다면 Package Settings에서 Visibility를 Public으로 변경한다.

## 7. Local Image를 지운 뒤 Pull 테스트

Remote Registry에 실제로 Image가 올라갔는지 확인하기 위해 Local Tag를 삭제한 뒤 GHCR에서 다시 내려받는다.

### 7-1. Local Container와 Image 삭제

```bash
docker rm keulkeul-ubuntu
docker rmi ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0 keulkeul-ubuntu-git:1.0 ubuntu:24.04
docker image ls
```

`docker image ls` 결과에서 `ubuntu`와 `keulkeul-ubuntu-git` Image가 사라졌는지 확인한다. 원본 Container를 먼저 삭제해야 해당 Image를 제거할 수 있다.

> [!NOTE]
> 다른 Container가 해당 Image를 사용 중이면 삭제할 수 없다. 실행 중인 Container가 있으면 먼저 해당 Container를 중지하고 삭제한다.

### 7-2. GHCR에서 Image 내려받기

```bash
docker pull ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0
docker image ls
```

Private Package라면 GHCR 로그인 상태가 필요하다. Pull이 완료되면 아래와 비슷한 Image가 표시된다.

```text
ghcr.io/USERNAME/keulkeul-ubuntu-git   1.0   ...   ...   ...
```

### 7-3. 내려받은 Image에서 Git 실행

```bash
docker run --rm ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0 git --version
```

Git 버전이 표시되면 Git이 설치된 상태로 Commit한 Image를 GHCR에서 다시 내려받아 실행한 것이다.

## 8. GitHub Repository와 Container Package 연결하기

GitHub Repository와 GitHub Packages의 Container Package는 별개의 Resource다. 명령어로 Image를 Push했다고 해서 같은 이름의 Repository와 자동으로 연결되지는 않는다.

```text
GitHub Repository
        │
        │ 별도의 Resource
        │
GitHub Container Package
```

Container Package를 Repository와 연결하려면 GitHub Package 화면에서 다음 작업을 수행한다.

1. `keulkeul-ubuntu-git` Package의 Settings를 연다.
2. Repository 연결 또는 접근 권한 설정 영역을 찾는다.
3. 사용할 GitHub Repository를 선택한다.
4. Package 화면에 연결된 Repository가 표시되는지 확인한다.

## 9. Docker Hub와 GitHub Container Registry 비교

| 항목 | Docker Hub | GitHub Container Registry |
| --- | --- | --- |
| Registry 주소 | `docker.io` | `ghcr.io` |
| Image 예시 | `USERNAME/keulkeul-ubuntu-git:1.0` | `ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0` |
| 로그인 | `docker login` | `docker login ghcr.io` |
| 저장 위치 | Docker Hub Repository | GitHub Packages Container Package |
| GitHub Repository 연결 | 별도 설정 | Package에서 연결 가능 |

## 10. 전체 흐름 정리

```text
Ubuntu Image
    ↓ docker pull
Container
    ↓ Git 설치
변경된 Container
    ↓ docker commit
keulkeul-ubuntu-git:1.0
    ↓ docker tag
ghcr.io/USERNAME/IMAGE:TAG
    ↓ docker login ghcr.io
GHCR 인증
    ↓ docker push
GitHub Packages
    ↓ docker pull
다른 환경의 Local Image
    ↓ docker run
Container 실행
```

`push`는 Registry가 이해할 수 있는 이름과 Tag를 Image에 붙인 뒤 원격 Registry에 업로드하는 과정이다.

## 11. 리소스 정리

이번 과제에서 사용한 Container와 Image를 확인한다.

```bash
docker ps -a
docker image ls
```

GHCR 로그인 정보를 Local Docker에서 제거한다.

```bash
docker logout ghcr.io
```

이번 과제에서 내려받은 Local Image를 삭제하려면 아래 명령어를 실행한다.

```bash
docker image rm ghcr.io/USERNAME/keulkeul-ubuntu-git:1.0
docker image ls
```
