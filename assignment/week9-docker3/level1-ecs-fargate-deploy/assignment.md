# Assignment: Docker Image를 ECS Fargate로 배포하기

Docker image를 ECR에 올리고, ECS Fargate Service에서 실행한 뒤 Application Load Balancer DNS로 접속한다.

참고 자료:
- https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-ecr-image.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/alb.html

> [!IMPORTANT]
> ECS, Load Balancer, NAT Gateway 같은 리소스는 비용이 발생할 수 있다. 실습 후 반드시 리소스를 삭제한다.

## 0. 사전 준비

- Docker Desktop
- AWS CLI
  - ECR 로그인과 Docker image push에만 사용
- AWS 계정 및 IAM 권한
  - ECR
  - ECS
  - EC2 VPC
  - Elastic Load Balancing
  - IAM
- 실습 리전: `ap-northeast-2`
- 제공된 샘플 앱: `app`

## 1. 샘플 서버 로컬 실행

cmd에서 `app` 폴더로 이동한다.

```cmd
cd /d "{ASSIGNMENT_PATH}\week9-docker3\level1-ecs-fargate-deploy\app"
```

Node 서버를 실행한다.

```cmd
npm start
```

새 cmd를 열고 확인한다.

```cmd
curl http://localhost:3000
```

정상 응답:

```json
{"message":"hello ecs","path":"/","container":"week9-level1"}
```

확인이 끝나면 서버를 실행한 cmd에서 `Ctrl + C`를 눌러 종료한다.

## 2. Docker image 만들기

`app` 폴더에서 Docker image를 build한다.

```cmd
docker build -t week9-ecs-app .
```

컨테이너로 실행한다.

```cmd
docker run -d -p 3000:3000 --name week9-ecs-container week9-ecs-app
```

확인한다.

```cmd
curl http://localhost:3000
```

컨테이너를 정리한다.

```cmd
docker stop week9-ecs-container
docker rm week9-ecs-container
```

## 3. ECR Repository 생성

AWS Console에서 ECR repository를 만든다.

1. AWS Console 오른쪽 위 리전이 `ap-northeast-2`인지 확인
2. 검색창에 **ECR** 입력
3. **Elastic Container Registry** 이동
4. 왼쪽 메뉴에서 **Repositories** 클릭
5. **Create repository** 클릭
6. 설정값 입력
    - Visibility settings: `Private`
    - Repository name: `week9-ecs-app`
    - Image tag mutability: `Mutable`
    - Encryption: 기본값
7. **Create repository** 클릭

Repository URI는 아래처럼 생겼다.

```text
{ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-app
```

### 3-1. ECR Repository에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Repository name | `week9-ecs-app` | Docker image를 저장할 ECR 저장소 이름 |
| Visibility | `Private` | 내 AWS 계정 안에서만 사용하는 image 저장소 |
| Repository URI | `{ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-app` | Docker tag, push, ECS image URI에 사용하는 주소 |

## 4. Docker image를 ECR에 push

AWS 계정 ID는 Console 오른쪽 위 계정 메뉴에서 확인하거나, 아래 명령어로 확인한다.

```cmd
aws sts get-caller-identity
```

아래 명령어에서 `{ACCOUNT_ID}`를 본인 계정 ID로 바꾼다.

ECR 로그인:

```cmd
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com
```

image tag 변경:

```cmd
docker tag week9-ecs-app:latest {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-app:latest
```

ECR push:

```cmd
docker push {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-app:latest
```

확인할 것:

- ECR repository에 `latest` image가 보이는가?
- Image URI를 복사했는가?

> [!NOTE]
> ECR 로그인과 image push 단계 때문에 AWS CLI가 필요하다. 원활한 실습을 위해 미리 설치해두는 것을 권장한다.

## 5. VPC 확인

이번 과제에서는 새 VPC를 만들지 않고 **Default VPC**를 사용한다.

이유:

```text
ECS 배포 핵심은 container image를 ECS에서 실행하는 것이다.
VPC를 직접 만드는 것은 다음 단계에서 다루는 것이 좋다.
```

확인할 것:

1. AWS Console 검색창에 **VPC** 입력
2. **Your VPCs** 이동
3. `Default VPC`가 있는지 확인
4. **Subnets**에서 default subnet이 2개 이상 있는지 확인
5. **Internet Gateways**에서 default VPC에 연결된 Internet Gateway가 있는지 확인

## 6. Target Group 생성

Application Load Balancer가 ECS task로 요청을 보내기 위해 Target Group을 만든다.

1. AWS Console 검색창에 **EC2** 입력
2. 왼쪽 메뉴에서 **Target Groups** 클릭
3. **Create target group** 클릭
4. 설정값 입력
    - Choose a target type: `IP addresses`
    - Target group name: `week9-ecs-tg`
    - Protocol: `HTTP`
    - Port: `3000`
    - VPC: Default VPC
    - Protocol version: `HTTP1`
    - Health check protocol: `HTTP`
    - Health check path: `/`
5. **Next** 클릭
6. Register targets 화면에서는 아무것도 등록하지 않는다.
7. **Create target group** 클릭

> [!NOTE]
> ECS Fargate는 task가 ENI를 직접 가지는 `awsvpc` network mode를 사용한다. 그래서 target type은 `Instance`가 아니라 `IP addresses`를 선택한다.

### 6-1. Target Group에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Target type | `IP addresses` | Fargate task의 private IP로 요청 전달 |
| Port | `3000` | container가 요청을 받는 port |
| Health check path | `/` | ALB가 container 상태를 확인할 경로 |

## 7. Application Load Balancer 생성

1. EC2 콘솔 왼쪽 메뉴에서 **Load Balancers** 클릭
2. **Create load balancer** 클릭
3. **Application Load Balancer**의 **Create** 클릭
4. 설정값 입력
    - Load balancer name: `week9-ecs-alb`
    - Scheme: `Internet-facing`
    - IP address type: `IPv4`
    - VPC: Default VPC
    - Mappings: 서로 다른 Availability Zone의 public subnet 2개 선택
5. Security Group 생성 또는 선택
    - 이름: `week9-ecs-alb-sg`
    - Inbound rule:

```text
Type: HTTP
Port: 80
Source: 0.0.0.0/0
```

6. Listener 설정
    - Protocol: `HTTP`
    - Port: `80`
    - Default action: `Forward to week9-ecs-tg`
7. **Create load balancer** 클릭

### 7-1. Application Load Balancer에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Scheme | `Internet-facing` | 인터넷에서 ALB로 접속 가능 |
| Listener | `HTTP:80` | 브라우저 요청을 받는 입구 |
| Default action | `Forward to week9-ecs-tg` | 받은 요청을 Target Group으로 전달 |
| Security Group inbound | `HTTP 80, 0.0.0.0/0` | 외부 사용자가 HTTP로 접속 가능 |

## 8. ECS Task Definition 생성

1. AWS Console 검색창에 **ECS** 입력
2. **Elastic Container Service** 이동
3. 왼쪽 메뉴에서 **Task definitions** 클릭
4. **Create new task definition** 클릭
5. 설정값 입력
    - Task definition family: `week9-ecs-task`
    - Launch type: `AWS Fargate`
    - Operating system/Architecture: `Linux/X86_64`
    - CPU: `.25 vCPU`
    - Memory: `.5 GB`
    - Task role: 비워둠
    - Task execution role: `ecsTaskExecutionRole`
6. Container 설정
    - Name: `week9-ecs-container`
    - Image URI: ECR에서 복사한 image URI
    - Container port: `3000`
    - Protocol: `TCP`
7. **Create** 클릭

### 8-1. Task Definition에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Family | `week9-ecs-task` | ECS task definition 이름 |
| Launch type | `AWS Fargate` | EC2 instance 없이 container 실행 |
| Image URI | ECR image URI | ECS가 실행할 Docker image |
| Container port | `3000` | Node app이 listen하는 port |

> [!IMPORTANT]
> Mac에서 ARM image로 build했다면 Fargate architecture를 `ARM64`로 맞추거나, Docker build 시 `--platform linux/amd64`를 사용한다.

## 9. ECS Cluster 생성

1. ECS 콘솔 왼쪽 메뉴에서 **Clusters** 클릭
2. **Create cluster** 클릭
3. 설정값 입력
    - Cluster name: `week9-ecs-cluster`
    - Infrastructure: `AWS Fargate`
4. **Create** 클릭

> [!NOTE]
> Cluster 생성 중 `Unable to assume the service linked role` 오류가 나면 ECS가 사용할 기본 IAM 역할이 없거나 생성 권한이 없는 상태다. IAM → Roles에서 `AWSServiceRoleForECS`가 있는지 확인한다. 없으면 관리자 권한이 있는 계정에서 아래 명령어로 생성한 뒤 다시 시도한다.

```cmd
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com
```

## 10. ECS Service 생성

1. `week9-ecs-cluster` 클릭
2. **Services** 탭 클릭
3. **Create** 클릭
4. 설정값 입력
    - Compute options: `Launch type`
    - Launch type: `FARGATE`
    - Platform version: `LATEST`
    - Application type: `Service`
    - Family: `week9-ecs-task`
    - Service name: `week9-ecs-service`
    - Scheduling strategy: `Replica`
    - Desired tasks: `1`
5. 배포 구성 설정
    - Availability Zone rebalancing: 기본값
    - Health check grace period: `30`
6. Networking 설정
    - VPC: Default VPC
    - Subnets: public subnet 2개 선택
    - Security group: 새로 생성
    - Security group name: `week9-ecs-service-sg`
    - Public IP: `Turned on`
7. ECS Service Security Group inbound rule

```text
Type: Custom TCP
Port: 3000
Source: week9-ecs-alb-sg
```

8. Load balancing 설정
    - Load balancer type: `Application Load Balancer`
    - Load balancer: `week9-ecs-alb`
    - Container: `week9-ecs-container 3000:3000`
    - Listener: `HTTP:80`
    - Target group: `week9-ecs-tg`
9. **Create** 클릭

### 10-1. ECS Service에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Scheduling strategy | `Replica` | 원하는 task 개수만큼 실행하고 유지 |
| Desired tasks | `1` | 실행할 container task 개수 |
| Health check grace period | `30` | 시작 직후 health check 실패를 잠깐 무시 |
| Public IP | `Turned on` | Fargate task가 public subnet에서 실행될 때 외부 통신 가능 |
| Security Group inbound | `3000, Source: week9-ecs-alb-sg` | ALB에서 오는 요청만 container로 허용 |
| Load balancer | `week9-ecs-alb` | 외부 요청을 ECS task로 연결 |
| Target group | `week9-ecs-tg` | ALB가 요청을 전달할 대상 그룹 |

## 11. 배포 확인

ECS Service의 task가 `Running`이 될 때까지 기다린다.

ALB DNS name을 복사한다.

1. EC2 콘솔
2. **Load Balancers**
3. `week9-ecs-alb` 선택
4. **DNS name** 복사

브라우저 또는 cmd에서 확인한다.

```cmd
curl http://{ALB_DNS_NAME}
```

정상 응답:

```json
{"message":"hello ecs","path":"/","container":"week9-level1"}
```

### 11-1. 코드 수정 후 다시 배포하는 방법

ECS에 한 번 배포한 뒤 코드를 수정하면, 실행 중인 task가 자동으로 바뀌지는 않는다.
로컬에서 Docker image를 다시 만들고, ECR에 다시 올린 뒤, ECS Service에 새 배포를 요청해야 한다.

1. `app` 폴더의 코드를 수정한다.

예:

```text
app/index.js
```

2. Docker image를 다시 build한다.

```cmd
docker build -t week9-ecs-app .
```

3. ECR 주소로 image tag를 다시 붙인다.

```cmd
docker tag week9-ecs-app:latest {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-app:latest
```

4. ECR에 다시 push한다.

```cmd
docker push {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-app:latest
```

5. ECS Service를 새로 배포한다.

```cmd
aws ecs update-service --region ap-northeast-2 --cluster week9-ecs-cluster --service week9-ecs-service --force-new-deployment
```

6. ALB DNS name으로 다시 확인한다.

```cmd
curl http://{ALB_DNS_NAME}
```

> [!NOTE]
> `latest`라는 tag 이름은 같아도, image를 다시 push하면 ECR의 실제 image digest가 바뀐다. `--force-new-deployment`를 실행하면 ECS가 새 task를 만들면서 ECR에서 최신 image를 다시 받아온다.


## 12. 실습 질문

아래 질문에 짧게 답한다.

1. ECR은 어떤 역할을 하는가?
2. ECS Cluster, Task Definition, Service는 각각 무엇인가?
3. Fargate를 사용하면 EC2 instance를 직접 만들지 않아도 되는 이유는 무엇인가?
4. Application Load Balancer는 왜 필요한가?
5. Fargate target group의 target type을 `IP addresses`로 선택하는 이유는 무엇인가?
6. Container port를 앱이 실제로 사용하는 port와 맞춰야 하는 이유는 무엇인가?
7. ALB Security Group과 ECS Service Security Group은 각각 어떤 inbound rule이 필요한가?

## 13. 리소스 정리

아래 순서로 삭제한다.

1. ECS Service 삭제
    - ECS → Clusters → `week9-ecs-cluster` → Services → `week9-ecs-service` 삭제
2. ECS Cluster 삭제
    - `week9-ecs-cluster` 삭제
3. Load Balancer 삭제
    - EC2 → Load Balancers → `week9-ecs-alb` 삭제
4. Target Group 삭제
    - EC2 → Target Groups → `week9-ecs-tg` 삭제
5. ECR Repository 삭제
    - ECR → Repositories → `week9-ecs-app` 삭제
6. Security Group 삭제
    - `week9-ecs-alb-sg`
    - `week9-ecs-service-sg`
7. 로컬 Docker image 삭제

```cmd
docker rmi week9-ecs-app:latest
docker rmi {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-app:latest
```

> [!IMPORTANT]
> Load Balancer는 켜져 있으면 비용이 계속 발생할 수 있다. 실습이 끝나면 꼭 삭제한다.


