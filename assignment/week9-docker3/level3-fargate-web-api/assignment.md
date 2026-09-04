# Assignment: ECS Fargate에서 Web + API 배포하기

Web image와 API image를 각각 ECR에 올리고, ECS Fargate Service 2개로 실행한다. Application Load Balancer는 `/` 요청은 web으로, `/api/*` 요청은 api로 보낸다.

> [!IMPORTANT]
> ECS와 Load Balancer는 비용이 발생할 수 있다. 실습 후 반드시 리소스를 삭제한다.

## 0. 사전 준비

- Docker Desktop
- AWS CLI
  - ECR 로그인과 Docker image push에 사용
- AWS 계정 및 IAM 권한
  - ECR
  - ECS
  - EC2 VPC
  - Elastic Load Balancing
  - IAM
- 실습 리전: `ap-northeast-2`
- Default VPC
- 제공된 샘플 앱
  - `web`
  - `api`

## 1. 전체 구조 이해

이번 구성은 하나의 ALB가 요청 경로에 따라 web과 api를 나누는 구조다.

```text
사용자
  ↓
Application Load Balancer
  ├─ /       → web service → web container
  └─ /api/*  → api service → api container
```

| 구성 요소 | 역할 |
| --- | --- |
| ECR web repository | web Docker image 저장 |
| ECR api repository | api Docker image 저장 |
| Web task definition | web container 실행 설정 |
| API task definition | api container 실행 설정 |
| Web service | web task 1개 실행 및 유지 |
| API service | api task 1개 실행 및 유지 |
| ALB listener | 외부 HTTP 요청을 받는 입구 |
| ALB listener rule | URL path에 따라 web/api로 요청 분리 |

## 2. 로컬에서 API 확인

먼저 API 서버가 정상 동작하는지 로컬에서 확인한다.

cmd에서 `api` 폴더로 이동한다.

```cmd
cd /d "{ASSIGNMENT_PATH}\week9-docker3\level3-fargate-web-api\api"
```

API 서버를 실행한다.

```cmd
npm start
```

새 cmd를 열고 확인한다.

```cmd
curl "http://localhost:3000/api/member?name=%EC%A0%95%EC%9C%A0%EC%A7%84"
```

정상 응답:

```json
{"name":"정유진","keulkeul_member":"yes"}
```

확인이 끝나면 API 서버를 실행한 cmd에서 `Ctrl + C`를 눌러 종료한다.

### 2-1. API에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| 실행 폴더 | `api` | Node API 서버 코드가 있는 위치 |
| Local port | `3000` | API 서버가 요청을 받는 port |
| API path | `/api/member` | 회원 여부를 확인하는 endpoint |
| Query string | `name=정유진` | 확인할 이름을 서버로 전달 |

## 3. Docker image 만들기

API image를 build한다.

```cmd
cd /d "{ASSIGNMENT_PATH}\week9-docker3\level3-fargate-web-api\api"
docker build -t week9-api .
```

Web image를 build한다.

```cmd
cd /d "{ASSIGNMENT_PATH}\week9-docker3\level3-fargate-web-api\web"
docker build -t week9-web .
```

생성된 image를 확인한다.

```cmd
docker images
```

### 3-1. Docker image에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| API image | `week9-api` | Node API 서버를 실행할 image |
| Web image | `week9-web` | 정적 web 화면을 Nginx로 실행할 image |
| Tag | `latest` | 이번 실습에서 사용할 image tag |

## 4. ECR Repository 2개 생성

AWS Console에서 ECR repository를 2개 만든다.

1. AWS Console 오른쪽 위 리전이 `ap-northeast-2`인지 확인
2. 검색창에 **ECR** 입력
3. **Elastic Container Registry** 이동
4. 왼쪽 메뉴에서 **Repositories** 클릭
5. **Create repository** 클릭
6. `week9-web` repository 생성
    - Visibility settings: `Private`
    - Repository name: `week9-web`
    - Image tag mutability: `Mutable`
    - Encryption: 기본값
7. 같은 방식으로 `week9-api` repository 생성

Repository URI는 아래처럼 생겼다.

```text
{ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-web
{ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-api
```

### 4-1. ECR Repository에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Web repository name | `week9-web` | web Docker image 저장소 |
| API repository name | `week9-api` | api Docker image 저장소 |
| Visibility | `Private` | 내 AWS 계정 안에서만 사용하는 image 저장소 |
| Image tag mutability | `Mutable` | 같은 tag 이름으로 image를 다시 push 가능 |
| Repository URI | ECR에서 복사 | Docker tag, push, ECS image URI에 사용 |

## 5. Docker image를 ECR에 push

AWS 계정 ID는 Console 오른쪽 위 계정 메뉴에서 확인하거나, 아래 명령어로 확인한다.

```cmd
aws sts get-caller-identity
```

아래 명령어에서 `{ACCOUNT_ID}`를 본인 계정 ID로 바꾼다.

ECR 로그인:

```cmd
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com
```

API image tag 변경:

```cmd
docker tag week9-api:latest {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-api:latest
```

API image push:

```cmd
docker push {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-api:latest
```

Web image tag 변경:

```cmd
docker tag week9-web:latest {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-web:latest
```

Web image push:

```cmd
docker push {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-web:latest
```

확인할 것:

- `week9-web` repository에 `latest` image가 보이는가?
- `week9-api` repository에 `latest` image가 보이는가?
- 두 image URI를 복사했는가?

> [!NOTE]
> ECR 로그인과 image push 단계 때문에 AWS CLI가 필요하다. 원활한 실습을 위해 미리 설치해두는 것을 권장한다.

## 6. VPC 확인

이번 과제에서는 새 VPC를 만들지 않고 **Default VPC**를 사용한다.

확인할 것:

1. AWS Console 검색창에 **VPC** 입력
2. **Your VPCs** 이동
3. `Default VPC`가 있는지 확인
4. **Subnets**에서 default subnet이 2개 이상 있는지 확인
5. **Internet Gateways**에서 default VPC에 연결된 Internet Gateway가 있는지 확인

## 7. Target Group 2개 생성

Application Load Balancer가 web service와 api service로 요청을 보내기 위해 Target Group을 2개 만든다.
Target Group은 ALB가 요청을 전달할 목적지 묶음이다.

이번 실습에서는 ECS Service가 나중에 task를 자동으로 등록하므로, Target Group을 만들 때 직접 target을 등록하지 않는다.

### 7-1. Web Target Group 생성

1. AWS Console 검색창에 **EC2** 입력
2. **EC2** 이동
3. 왼쪽 메뉴에서 **Target Groups** 클릭
4. **Create target group** 클릭
5. **Basic configuration** 설정
    - Choose a target type: `IP addresses`
    - Target group name: `week9-web-tg`
    - Protocol: `HTTP`
    - Port: `80`
    - VPC: Default VPC
    - Protocol version: `HTTP1`
6. **Health checks** 설정
    - Health check protocol: `HTTP`
    - Health check path: `/`
7. **Next** 클릭
8. **Register targets** 화면에서는 아무것도 선택하지 않는다.
9. **Create target group** 클릭

### 7-2. API Target Group 생성

1. EC2 → **Target Groups** 화면에서 **Create target group** 클릭
2. **Basic configuration** 설정
    - Choose a target type: `IP addresses`
    - Target group name: `week9-api-tg`
    - Protocol: `HTTP`
    - Port: `3000`
    - VPC: Default VPC
    - Protocol version: `HTTP1`
3. **Health checks** 설정
    - Health check protocol: `HTTP`
    - Health check path: `/api/member`
4. **Next** 클릭
5. **Register targets** 화면에서는 아무것도 선택하지 않는다.
6. **Create target group** 클릭

> [!IMPORTANT]
> `week9-api-tg`의 port는 `80`이 아니라 `3000`이다. API container가 Node 서버이고 3000번 port에서 실행되기 때문이다.

### 7-3. Target Group에서 확인할 항목

| Target group | Target type | Protocol | Port | Health check path | 역할 |
| --- | --- | --- | --- | --- | --- |
| `week9-web-tg` | `IP addresses` | `HTTP` | `80` | `/` | web container로 요청 전달 |
| `week9-api-tg` | `IP addresses` | `HTTP` | `3000` | `/api/member` | api container로 요청 전달 |

> [!NOTE]
> ECS Fargate는 task가 ENI를 직접 가지는 `awsvpc` network mode를 사용한다. 그래서 target type은 `Instance`가 아니라 `IP addresses`를 선택한다.

## 8. Application Load Balancer 생성

1. EC2 콘솔 왼쪽 메뉴에서 **Load Balancers** 클릭
2. **Create load balancer** 클릭
3. **Application Load Balancer**의 **Create** 클릭
4. **Basic configuration** 설정
    - Load balancer name: `week9-web-api-alb`
    - Scheme: `Internet-facing`
    - IP address type: `IPv4`
5. **Network mapping** 설정
    - VPC: Default VPC
    - Mappings: 서로 다른 Availability Zone의 public subnet 2개 선택
6. **Security groups** 설정
    - **Create a new security group** 클릭
    - Security group name: `week9-web-api-alb-sg`
    - Description: `week9 web api alb security group`
    - VPC: Default VPC
    - Inbound rule 추가:

```text
Type: HTTP
Port: 80
Source: 0.0.0.0/0
```

7. 다시 ALB 생성 화면으로 돌아와서 Security group에 `week9-web-api-alb-sg`가 선택되어 있는지 확인
8. **Listeners and routing** 설정
    - Protocol: `HTTP`
    - Port: `80`
    - Default action: `Forward to week9-web-tg`
9. **Create load balancer** 클릭

### 8-1. Application Load Balancer에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Load balancer name | `week9-web-api-alb` | web/api 앞에 놓이는 외부 접속 입구 |
| Scheme | `Internet-facing` | 인터넷에서 ALB로 접속 가능 |
| Listener | `HTTP:80` | 브라우저 요청을 받는 port |
| Default action | `Forward to week9-web-tg` | `/` 요청을 web으로 전달 |
| Security Group inbound | `HTTP 80, 0.0.0.0/0` | 외부 사용자가 HTTP로 접속 가능 |

## 9. ALB Listener Rule 추가

ALB를 만들면 기본적으로 `HTTP:80` listener가 하나 있다. 이 listener에 `/api/*` 요청을 API Target Group으로 보내는 rule을 추가한다.

1. EC2 콘솔 왼쪽 메뉴에서 **Load Balancers** 클릭
2. `week9-web-api-alb` 선택
3. **Listeners and rules** 탭 클릭
4. `HTTP:80` listener 클릭
5. **Rules** 탭에서 **Add rule** 클릭
6. Rule name 입력
    - Rule name: `api-rule`
7. 조건 추가
    - Condition type: `Path`
    - Match type: `Wildcard match`
    - Path: `/api/*`
8. Action 설정
    - Action: `Forward to target groups`
    - Target group: `week9-api-tg`
    - Weight: `1`
9. Priority 설정
    - Priority: `1`
10. **Create** 또는 **Save** 클릭

> [!IMPORTANT]
> 새 listener를 하나 더 만드는 것이 아니라, 기존 `HTTP:80` listener 안에 rule을 추가한다. `HTTP:80` listener는 한 ALB에 같은 조건으로 중복 생성할 수 없다.

### 9-1. Listener Rule에서 확인할 항목

| 요청 경로 | 이동할 Target Group | 의미 |
| --- | --- | --- |
| `/api/*` | `week9-api-tg` | API 요청은 API service로 전달 |
| 그 외 요청 | `week9-web-tg` | 기본 요청은 web service로 전달 |

## 10. ECS Cluster 생성

1. ECS 콘솔 왼쪽 메뉴에서 **Clusters** 클릭
2. **Create cluster** 클릭
3. 설정값 입력
    - Cluster name: `week9-web-api-cluster`
    - Infrastructure: `AWS Fargate`
4. **Create** 클릭

> [!NOTE]
> Cluster 생성 중 `Unable to assume the service linked role` 오류가 나면 ECS가 사용할 기본 IAM 역할이 없거나 생성 권한이 없는 상태다. IAM → Roles에서 `AWSServiceRoleForECS`가 있는지 확인한다. 없으면 관리자 권한이 있는 계정에서 아래 명령어로 생성한 뒤 다시 시도한다.

```cmd
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com
```

## 11. ECS Task Definition 2개 생성

Web service와 API service는 실행할 image와 port가 다르므로 Task Definition을 2개 만든다.

### 11-1. Web Task Definition 생성

1. ECS 콘솔 왼쪽 메뉴에서 **Task definitions** 클릭
2. **Create new task definition** 클릭
3. **Task definition configuration** 설정
    - Task definition family: `week9-web-task`
4. **Infrastructure requirements** 설정
    - Launch type: `AWS Fargate`
    - Operating system/Architecture: `Linux/X86_64`
    - CPU: `.25 vCPU`
    - Memory: `.5 GB`
    - Task role: 비워둠
    - Task execution role: `ecsTaskExecutionRole`
5. **Container - 1** 설정
    - Name: `week9-web-container`
    - Image URI: ECR에서 복사한 `week9-web` image URI
    - Container port: `80`
    - Protocol: `TCP`
    - App protocol: `HTTP`
6. **Logging**은 기본값 사용
7. **Create** 클릭

### 11-2. API Task Definition 생성

1. ECS 콘솔 왼쪽 메뉴에서 **Task definitions** 클릭
2. **Create new task definition** 클릭
3. **Task definition configuration** 설정
    - Task definition family: `week9-api-task`
4. **Infrastructure requirements** 설정
    - Launch type: `AWS Fargate`
    - Operating system/Architecture: `Linux/X86_64`
    - CPU: `.25 vCPU`
    - Memory: `.5 GB`
    - Task role: 비워둠
    - Task execution role: `ecsTaskExecutionRole`
5. **Container - 1** 설정
    - Name: `week9-api-container`
    - Image URI: ECR에서 복사한 `week9-api` image URI
    - Container port: `3000`
    - Protocol: `TCP`
    - App protocol: `HTTP`
6. **Logging**은 기본값 사용
7. **Create** 클릭

### 11-3. Task Definition에서 확인할 항목

| 항목 | Web | API |
| --- | --- | --- |
| Family | `week9-web-task` | `week9-api-task` |
| Launch type | `AWS Fargate` | `AWS Fargate` |
| CPU | `.25 vCPU` | `.25 vCPU` |
| Memory | `.5 GB` | `.5 GB` |
| Task role | 비워둠 | 비워둠 |
| Task execution role | `ecsTaskExecutionRole` | `ecsTaskExecutionRole` |
| Container name | `week9-web-container` | `week9-api-container` |
| Container port | `80` | `3000` |

> [!IMPORTANT]
> Web container는 Nginx가 80번 port로 요청을 받고, API container는 Node 서버가 3000번 port로 요청을 받는다. Target Group port와 Container port를 서로 맞춰야 한다.

## 12. ECS Service 2개 생성

Service는 Task Definition을 실제로 실행하고, 원하는 개수의 task를 계속 유지한다. Web service와 API service를 각각 만든다.

### 12-1. 공통 Service 설정

두 Service를 만들 때 아래 값은 공통으로 사용한다.

| 항목 | 값 |
| --- | --- |
| Compute options | `Launch type` |
| Launch type | `FARGATE` |
| Platform version | `LATEST` |
| Application type | `Service` |
| Scheduling strategy | `Replica` |
| Desired tasks | `1` |
| Availability Zone rebalancing | 기본값 |
| Health check grace period | `30` |
| VPC | Default VPC |
| Subnets | public subnet 2개 |
| Public IP | `Turned on` |

### 12-2. Web Service 생성

1. `week9-web-api-cluster` 클릭
2. **Services** 탭 클릭
3. **Create** 클릭
4. **Environment** 설정
    - Compute options: `Launch type`
    - Launch type: `FARGATE`
    - Platform version: `LATEST`
5. **Deployment configuration** 설정
    - Family: `week9-web-task`
    - Service name: `week9-web-service`
    - Desired tasks: `1`
    - Scheduling strategy: `Replica`
    - Health check grace period: `30`
6. **Networking** 설정
    - VPC: Default VPC
    - Subnets: public subnet 2개 선택
    - Security group: 새로 생성
    - Security group name: `week9-web-sg`
    - Public IP: `Turned on`
7. Web Service Security Group inbound rule 추가

```text
Type: HTTP
Port: 80
Source: week9-web-api-alb-sg
```

8. **Load balancing** 설정
    - Load balancing: 체크
    - Load balancer type: `Application Load Balancer`
    - Application Load Balancer: `Use an existing load balancer`
    - Load balancer: `week9-web-api-alb`
    - Container: `week9-web-container 80:80`
    - Listener: `Use an existing listener`
    - Listener: `HTTP:80`
    - Target group: `Use an existing target group`
    - Target group: `week9-web-tg`
9. **Create** 클릭

### 12-3. API Service 생성

1. `week9-web-api-cluster` 클릭
2. **Services** 탭 클릭
3. **Create** 클릭
4. **Environment** 설정
    - Compute options: `Launch type`
    - Launch type: `FARGATE`
    - Platform version: `LATEST`
5. **Deployment configuration** 설정
    - Family: `week9-api-task`
    - Service name: `week9-api-service`
    - Desired tasks: `1`
    - Scheduling strategy: `Replica`
    - Health check grace period: `30`
6. **Networking** 설정
    - VPC: Default VPC
    - Subnets: public subnet 2개 선택
    - Security group: 새로 생성
    - Security group name: `week9-api-sg`
    - Public IP: `Turned on`
7. API Service Security Group inbound rule 추가

```text
Type: Custom TCP
Port: 3000
Source: week9-web-api-alb-sg
```

8. **Load balancing** 설정
    - Load balancing: 체크
    - Load balancer type: `Application Load Balancer`
    - Application Load Balancer: `Use an existing load balancer`
    - Load balancer: `week9-web-api-alb`
    - Container: `week9-api-container 3000:3000`
    - Listener: `Use an existing listener`
    - Listener: `HTTP:80`
    - Target group: `Use an existing target group`
    - Target group: `week9-api-tg`
9. **Create** 클릭

> [!NOTE]
> Web Service와 API Service에서 Security Group을 하나로 같이 써도 된다. 하나로 쓸 경우 inbound rule에 `80`과 `3000`을 둘 다 추가하고, Source는 둘 다 `week9-web-api-alb-sg`로 설정한다.

### 12-4. ECS Service에서 확인할 항목

| 항목 | Web Service | API Service |
| --- | --- | --- |
| Service name | `week9-web-service` | `week9-api-service` |
| Family | `week9-web-task` | `week9-api-task` |
| Desired tasks | `1` | `1` |
| Public IP | `Turned on` | `Turned on` |
| Security Group inbound | `80, Source: week9-web-api-alb-sg` | `3000, Source: week9-web-api-alb-sg` |
| Load balancer | `week9-web-api-alb` | `week9-web-api-alb` |
| Target group | `week9-web-tg` | `week9-api-tg` |

## 13. 배포 확인

ECS Service 2개의 task가 모두 `Running`이 될 때까지 기다린다.

ALB DNS name을 복사한다.

1. EC2 콘솔
2. **Load Balancers**
3. `week9-web-api-alb` 선택
4. **DNS name** 복사

cmd에서 확인한다.

```cmd
curl http://{ALB_DNS_NAME}
curl "http://{ALB_DNS_NAME}/api/member?name=%EC%A0%95%EC%9C%A0%EC%A7%84"
```

정상 응답:

```text
첫 번째 요청: HTML 화면
두 번째 요청: {"name":"정유진","keulkeul_member":"yes"}
```

브라우저에서 `http://{ALB_DNS_NAME}`에 접속한 뒤 이름을 입력하고 **확인** 버튼을 눌러도 된다.

### 13-1. 문제가 생기면 확인할 항목

| 증상 | 확인할 곳 |
| --- | --- |
| web 화면이 안 뜸 | `week9-web-tg` health check, web service task 상태 |
| API 응답이 안 옴 | Listener rule의 `/api/*`, `week9-api-tg` port `3000` |
| target이 unhealthy | container port, target group port, security group inbound |
| ALB DNS 접속이 안 됨 | ALB security group inbound `HTTP 80, 0.0.0.0/0` |

## 14. 코드 수정 후 다시 배포하는 방법

ECS에 한 번 배포한 뒤 코드를 수정하면, 실행 중인 task가 자동으로 바뀌지는 않는다. 수정한 쪽의 Docker image를 다시 만들고, ECR에 다시 올린 뒤, 해당 ECS Service에 새 배포를 요청해야 한다.

### 14-1. API 코드를 수정한 경우

```cmd
cd /d "{ASSIGNMENT_PATH}\week9-docker3\level3-fargate-web-api\api"
docker build -t week9-api .
docker tag week9-api:latest {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-api:latest
docker push {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-api:latest
aws ecs update-service --region ap-northeast-2 --cluster week9-web-api-cluster --service week9-api-service --force-new-deployment
```

### 14-2. Web 코드를 수정한 경우

```cmd
cd /d "{ASSIGNMENT_PATH}\week9-docker3\level3-fargate-web-api\web"
docker build -t week9-web .
docker tag week9-web:latest {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-web:latest
docker push {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-web:latest
aws ecs update-service --region ap-northeast-2 --cluster week9-web-api-cluster --service week9-web-service --force-new-deployment
```

> [!NOTE]
> `latest`라는 tag 이름은 같아도, image를 다시 push하면 ECR의 실제 image digest가 바뀐다. `--force-new-deployment`를 실행하면 ECS가 새 task를 만들면서 ECR에서 최신 image를 다시 받아온다.

## 15. 실습 질문

아래 질문에 짧게 답한다.

1. Web service와 API service를 나누는 이유는 무엇인가?
2. ALB listener rule에서 `/api/*` 조건은 어떤 역할을 하는가?
3. 기본 listener action은 왜 web target group으로 설정하는가?
4. Fargate target group의 target type을 `IP addresses`로 선택하는 이유는 무엇인가?
5. Web container와 API container의 port가 다른 이유는 무엇인가?
6. Security Group source를 `0.0.0.0/0`이 아니라 ALB Security Group으로 제한하는 이유는 무엇인가?
7. 코드를 수정한 뒤 Docker image를 다시 build, push해야 하는 이유는 무엇인가?

## 16. 리소스 정리

아래 순서로 삭제한다.

1. ECS Service 삭제
    - ECS → Clusters → `week9-web-api-cluster` → Services
    - `week9-web-service`
    - `week9-api-service`
2. ECS Cluster 삭제
    - `week9-web-api-cluster`
3. Load Balancer 삭제
    - EC2 → Load Balancers → `week9-web-api-alb`
4. Target Group 삭제
    - EC2 → Target Groups
    - `week9-web-tg`
    - `week9-api-tg`
5. ECR Repository 삭제
    - ECR → Repositories
    - `week9-web`
    - `week9-api`
6. Security Group 삭제
    - `week9-web-api-alb-sg`
    - `week9-web-sg`
    - `week9-api-sg`
7. 로컬 Docker image 삭제

```cmd
docker rmi week9-web:latest
docker rmi week9-api:latest
docker rmi {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-web:latest
docker rmi {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-api:latest
```

> [!IMPORTANT]
> Load Balancer는 켜져 있으면 비용이 계속 발생할 수 있다. 실습이 끝나면 꼭 삭제한다.
