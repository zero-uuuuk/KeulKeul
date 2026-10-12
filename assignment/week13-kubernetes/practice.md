# <Kubernetes 배포→자가복구→부하분산→롤백>

웹 서버 Pod 3개를 배포하고 Service 부하분산, Pod 삭제 후 자가복구, 이미지 업데이트와 실패한 배포의 롤백을 확인한다.

### 0. 사전 준비

- Docker Desktop, Minikube, kubectl
- Google hello-app 샘플 이미지를 사용하므로 앱 코드 수정이나 이미지 빌드는 필요 없다!
- Mac은 Homebrew 설치가 필요

 `<POD_이름>`과 URL은 실제 값으로 바꾼다.

**설치할 도구와 실습에서 하는 일**

| 도구 | 필요한 이유 | 사용할 명령 |
| --- | --- | --- |
| Docker Desktop | Minikube의 Docker 드라이버에 필요한 Linux 컨테이너 엔진 제공 | `docker info` |
| Minikube | 로컬 Kubernetes 클러스터 생성·접속·중지 | `minikube start`, `minikube service`, `minikube stop` |
| kubectl | Kubernetes API Server에 요청을 보내 리소스 생성·조회·수정·삭제 | `kubectl create`, `get`, `set image`, `delete` , `rollout` |

**Mac 터미널 3**

```
open -a Docker
```

```
brew install minikube kubectl

docker info
minikube version
kubectl version --client
```

**Windows 터미널 3**

```
winget install --exact --id Kubernetes.minikube
winget install --exact --id Kubernetes.kubectl
```

```
docker info
minikube version
kubectl version --client
```

`docker info`에 서버 연결 오류가 없고 Minikube·kubectl 버전이 출력되는지 확인한다.

앞으로 사용할 터미널 3개:

| 터미널 | 역할 |
| --- | --- |
| 터미널 1 | Pod 직접 접속 및 Minikube 서비스 터널 유지 |
| 터미널 2 | 반복 요청을 통해 Hostname과 버전 관찰 |
| 터미널 3 | Pod 삭제, 이미지 업데이트 및 롤백 실행 |

---

### 1. **Minikube 시작 및 실습 공간 생성**

**터미널 3**

```
minikube start --driver=docker

kubectl config use-context minikube

kubectl config current-context

kubectl get nodes

kubectl create namespace week13-kubernetes

```

**확인할 것:**

- 현재 context가 `minikube`인가?
- Node의 `STATUS`가 `Ready`인가?
- `namespace/week13-kubernetes created`가 출력되는가?

---

### 2. 웹 서버 3개 배포 및 Pod 직접 접속

**터미널 3**

```
kubectl -n week13-kubernetes create deployment hello-api --image=gcr.io/google-samples/hello-app:1.0 --replicas=3

kubectl -n week13-kubernetes rollout status deployment/hello-api --timeout=120s

kubectl -n week13-kubernetes get deployment,replicaset,pods
```

Deployment의 `READY 3/3`을 확인한다. Pod 각각은 `READY 1/1`이다. 실패하면 다음 명령어로 원인을 확인한다.

```
kubectl -n week13-kubernetes describe pods
```

**터미널 1**에서 특정 Pod에 연결한다.

```
kubectl -n week13-kubernetes port-forward pod/<POD_이름> 8080:8080
```

**터미널 2**에서 다음 명령어를 여러 번 실행한다.

**Mac**

```
curl http://localhost:8080
```

**Windows**

```
curl.exe http://localhost:8080
```

Hostname이 같은지 확인하고 터미널 1의 port-forward를 `Ctrl+C`로 종료한다.

---

### 3. Service 생성 및 부하분산 확인

**터미널1**

```
kubectl -n week13-kubernetes expose deployment hello-api --type=NodePort --port=8080 --target-port=8080

minikube service hello-api -n week13-kubernetes --url
```

**결과:**

```
노드의 NodePort (자동 할당)
          ↓
Service :8080
          ↓
Pod A :8080 / Pod B :8080 / Pod C :8080
```

**터미널 1**에서 터널을 유지한다. 출력된 URL을 아래 실제 URL 자리에 넣고 터미널 2에서 실행한다.

**Mac**

```
SERVICE_URL='http://127.0.0.1:실제_포트'
while true; do
  curl --max-time 3 "$SERVICE_URL"
  sleep 1
done
```

**Windows PowerShell**

```
$serviceUrl = 'http://127.0.0.1:실제_포트'
while ($true) {
  curl.exe --max-time 3 $serviceUrl
  Start-Sleep -Seconds 1
}
```

여러 Hostname이 나타나는지 관찰한다. 순번·균등한 횟수는 보장하지 않는다.

```
내 컴퓨터 <실제포트><- Minikube가 내 컴퓨터에 만든 접속용 터널 포트
           ↓ Minikube 터널
Service :8080
           ↓
Pod 3개 중 하나의 :8080
```

### 3-1. Pod 삭제로 자가복구 확인

**터미널 2**의 반복 요청을 유지하고, 터미널 3에서 hello-api Pod 하나를 삭제한다.

```
kubectl -n week13-kubernetes get pods -l app=hello-api

kubectl -n week13-kubernetes delete pod <POD_이름>

kubectl -n week13-kubernetes get pods -l app=hello-api -w
```

준비된 Pod가 다시 3개가 되면 터미널 3에서 `Ctrl+C`로 감시만 종료한다.

응답에 새 이름이 나타나는지 확인한다.

진행 중 연결과 네트워크 전환으로 요청이 일시적으로 실패할 수 있다.

### 4. 이미지 업데이트 및 롤백

**터미널 3**에서 실행한다.

```
kubectl -n week13-kubernetes set image deployment/hello-api hello-app=gcr.io/google-samples/hello-app:2.0

kubectl -n week13-kubernetes rollout status deployment/hello-api --timeout=120s

kubectl -n week13-kubernetes get pods -l app=hello-api

```

반복 요청이 `Version: 2.0.0`으로 바뀌는지 확인한다.

**정상 v2 배포 완료와 READY 3/3을 확인한 뒤** 다음 명령을 실행한다.

```
kubectl -n week13-kubernetes set image deployment/hello-api hello-app=gcr.io/google-samples/hello-app:99.0

kubectl -n week13-kubernetes get pods -l app=hello-api -w
```

`ErrImagePull` : 이미지 다운로드 실패

또는 `ImagePullBackOff` : 잠시 기다린 뒤 다운로드 재시도

를 확인하고 `Ctrl+C`로 감시를 종료한다.



아래 명령의 Events에서 이미지 태그 오류인지 확인한다.

```
kubectl -n week13-kubernetes describe pod <실패한_POD_이름>
```

기본 RollingUpdate 설정과 복제본 3개에서는 새 Pod가 준비되지 않으므로 기존 정상 v2 Pod가 유지된다.

**롤백 실행**

**터미널3**

```
kubectl -n week13-kubernetes rollout history deployment/hello-api
kubectl -n week13-kubernetes rollout undo deployment/hello-api
kubectl -n week13-kubernetes rollout status deployment/hello-api --timeout=120s
kubectl -n week13-kubernetes get deployment hello-api -o jsonpath='{.spec.template.spec.containers[*].image}'
```

태그가 `2.0`인지 확인한다. 직전 정상 revision으로 되돌렸으므로 v1이 아닌 v2다.

운영 수준의 무중단 배포에는 readiness probe와 정상 종료 처리도 필요하다.

- 자동롤백도 가능하다.
    
    정상 v2 배포 상태에서 실행한다. 이 스크립트가 배포 완료를 기다리고, 실패하면 롤백 명령을 실행한다. Kubernetes 자체의 기본 자동 롤백 기능은 아니다.
    
    ```powershell
    kubectl -n week13-kubernetes set image deployment/hello-api hello-app=gcr.io/google-samples/hello-app:99.0
    
    if ($LASTEXITCODE -ne 0) {
        throw "이미지 변경 명령 실패"
    }
    
    kubectl -n week13-kubernetes rollout status deployment/hello-api --timeout=120s
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "배포 완료 실패: 이전 버전으로 롤백합니다."
    
        kubectl -n week13-kubernetes rollout undo deployment/hello-api
        if ($LASTEXITCODE -ne 0) {
            throw "롤백 명령 실패"
        }
    
        kubectl -n week13-kubernetes rollout status deployment/hello-api --timeout=120s
        if ($LASTEXITCODE -ne 0) {
            throw "롤백 완료 확인 실패"
        }
    }
    ```
    

### 5. 리소스 정리

반복 요청·터널·감시를 모두 `Ctrl+C`로 종료한다.

**터미널 3**에서 아래 명령을 실행한다. 현재 context가 실습용 Minikube인지 확인한다.

```
kubectl config current-context

kubectl delete namespace week13-kubernetes

minikube stop
```

namespace 안의 실습 리소스를 삭제한다.

`minikube delete`는 다른 실습 리소스까지 지울 수 있어 기본 정리에 포함하지 않는다.

이전에 장애 재현 실습을 실행했다면 같은 namespace에 남아 있는 해당 리소스도 함께 삭제된다.

### 6. 완료 확인

- [ ]  Deployment의 `READY 3/3`을 확인했다.
- [ ]  Pod 직접 접속에서는 동일한 Hostname이 응답했다.
- [ ]  Service 접속에서는 여러 Hostname이 응답했다.
- [ ]  Pod 삭제 후 새로운 Pod가 생성되어 준비된 Pod가 다시 3개가 됐다.
- [ ]  v2 업데이트 후 `Version: 2.0.0`을 확인했다.
- [ ]  잘못된 이미지의 다운로드 실패와 v2 롤백을 확인했다.
- [ ]  실습 namespace를 삭제했다.

### 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| Docker 연결 실패 | Docker Desktop 실행, Linux 엔진 준비 상태 |
| `hello-api already exists` | 이전 실습 리소스가 남아 있는지 확인 |
| Pod가 `Pending` | `describe pod`의 Events에서 자원 부족 등 확인 |
| `ImagePullBackOff` | 99.0 태그 실험 외에는 이미지 이름, 네트워크, Events 확인 |
| Service 접속 실패 | Minikube 터널 유지 여부, 실제 URL, Pod READY 상태 |
| 반복 요청에 한 Hostname만 나옴 | Pod port-forward 대신 Minikube Service URL로 요청하는지 확인 |

### 참고 자료

- [Minikube 설치](https://minikube.sigs.k8s.io/docs/start/)
- [Minikube 서비스 접속](https://minikube.sigs.k8s.io/docs/handbook/accessing/)
- [Deployment 업데이트와 롤백](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)