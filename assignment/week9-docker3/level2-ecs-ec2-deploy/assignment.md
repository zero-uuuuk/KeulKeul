# Assignment: ECS EC2 기반으로 Docker Container 배포하기

Level 2용 Docker image를 새로 만들고, 이번에는 Fargate가 아니라 EC2 기반 ECS Cluster에서 실행한다.

참고 자료:
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch_types.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/alb.html

> [!IMPORTANT]
> ECS, EC2, Auto Scaling Group, Load Balancer는 비용이 발생할 수 있다. 실습 후 반드시 리소스를 삭제한다.

## 0. 사전 준비

- Docker Desktop
- AWS CLI
- Level 2용 app 폴더
  - `app/Dockerfile`
  - `app/index.js`
  - `app/package.json`
- AWS 계정 및 IAM 권한
  - ECS
  - EC2
  - Auto Scaling
  - Elastic Load Balancing
  - IAM
- 실습 리전: `ap-northeast-2`
- Default VPC
- Default VPC의 public subnet 2개 이상

## 1. Level 2용 Docker image 준비

이번 Level에서는 Level 1 image를 재사용하지 않고, Level 2용 image를 새로 만든다.

### 1-1. 로컬에서 실행 확인

`app` 폴더로 이동한다.

```cmd
cd /d "{ASSIGNMENT_PATH}\week9-docker3\level2-ecs-ec2-deploy\app"
```

Node.js로 먼저 실행한다.

```cmd
npm start
```

새 cmd를 열고 확인한다.

```cmd
curl http://localhost:3000
```

정상 응답:

```json
{"message":"hello ecs ec2","path":"/","container":"week9-level2"}
```

확인이 끝나면 서버를 실행한 cmd에서 `Ctrl + C`를 눌러 종료한다.

### 1-2. Docker image 만들기

`app` 폴더에서 Docker image를 build한다.

```cmd
docker build -t week9-ecs-ec2-app .
```

컨테이너로 실행한다.

```cmd
docker run -d -p 3000:3000 --name week9-ecs-ec2-container week9-ecs-ec2-app
```

확인한다.

```cmd
curl http://localhost:3000
```

컨테이너를 정리한다.

```cmd
docker stop week9-ecs-ec2-container
docker rm week9-ecs-ec2-container
```

### 1-3. ECR Repository 생성

AWS Console에서 ECR Repository를 새로 만든다.

1. AWS Console 오른쪽 위 리전이 `ap-northeast-2`인지 확인
2. 검색창에 **ECR** 입력
3. **Elastic Container Registry** 이동
4. 왼쪽 메뉴에서 **Repositories** 클릭
5. **Create repository** 클릭
6. 설정값 입력
    - Visibility settings: `Private`
    - Repository name: `week9-ecs-ec2-app`
    - Image tag mutability: `Mutable`
    - Encryption: 기본값
7. **Create repository** 클릭

Repository URI는 아래처럼 생겼다.

```text
{ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-ec2-app
```

### 1-3-1. ECR Repository에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Repository name | `week9-ecs-ec2-app` | Docker image를 저장할 ECR 저장소 이름 |
| Visibility | `Private` | 내 AWS 계정 안에서만 사용하는 image 저장소 |
| Repository URI | `{ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-ec2-app` | Docker tag, push, ECS image URI에 사용하는 주소 |

### 1-4. ECR에 image push

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
docker tag week9-ecs-ec2-app:latest {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-ec2-app:latest
```

ECR push:

```cmd
docker push {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-ec2-app:latest
```

확인할 것:

- ECR repository에 `latest` image가 보이는가?
- Image URI를 복사했는가?

> [!NOTE]
> ECR 로그인과 image push 단계 때문에 AWS CLI가 필요하다. 원활한 실습을 위해 미리 설치해두는 것을 권장한다.

## 2. 전체 구조 이해

이번 구성은 아래 흐름으로 동작한다.

```text
사용자
  ↓
Application Load Balancer
  ↓
ECS Service
  ↓
EC2 instance
  ↓
Docker container
```

Level 1과 가장 큰 차이는 container가 실행되는 위치다.

| 구분 | Level 1 | Level 2 |
| --- | --- | --- |
| ECS 실행 방식 | Fargate | EC2 |
| 서버 관리 | AWS가 관리 | EC2 instance가 필요 |
| Network mode | `awsvpc` | `bridge` |
| Target Group type | `IP addresses` | `Instances` |
| 포트 연결 | Task IP와 container port | EC2 instance port와 container port |

## 3. ECS Cluster 생성

1. AWS Console 검색창에 **ECS** 입력
2. **Elastic Container Service** 이동
3. 왼쪽 메뉴에서 **Clusters** 클릭
4. **Create cluster** 클릭
5. **Cluster configuration** 설정
    - Cluster name: `week9-ecs-ec2-cluster`
6. **Select how to source compute capacity** 설정
    - `Fargate and self-managed instances`
7. **Auto Scaling group (ASG)** 설정
    - `Create new Auto Scaling group`
8. **Provisioning model** 설정
    - `On-Demand`
9. **Container instance Amazon Machine Image (AMI)** 설정
    - `Amazon Linux 2023`
10. **EC2 instance type** 설정
    - `t3.micro`
11. **EC2 instance role** 설정
    - `Create new role` 또는 `Create new instance profile`
    - 기본값으로 생성
12. **Desired capacity** 설정
    - Minimum: `1`
    - Maximum: `1`
13. **SSH key pair** 설정
    - 이미 만든 key pair가 있으면 선택
14. **Root EBS volume size** 설정
    - 기본값 사용
15. **Network settings** 설정
    - VPC: Default VPC
    - Subnets: public subnet 2개 선택
    - Security group: `Create a new security group`
    - Security group name: `week9-ecs-ec2-sg`
    - Description: `ECS EC2 container instance security group`
16. Monitoring, Encryption, Tags는 기본값 사용
17. **Create** 클릭

> [!NOTE]
> 이 Level에서는 EC2 instance 위에서 container가 실행되는 구조를 확인한다. 그래서 `Fargate and self-managed instances`를 선택한다.

### 3-1. Cluster에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Cluster name | `week9-ecs-ec2-cluster` | ECS Service와 Task가 실행될 논리 공간 |
| Compute capacity | `Fargate and self-managed instances` | 직접 관리하는 EC2 instance를 cluster 용량으로 사용 |
| Provisioning model | `On-Demand` | 실습 중 안정적으로 EC2 instance 실행 |
| AMI | `Amazon Linux 2023` | ECS container instance용 OS |
| EC2 instance type | `t3.micro` | 실습용 ECS worker instance |
| Desired capacity | `1 / 1` | EC2 instance 1개만 유지 |
| Security group | `week9-ecs-ec2-sg` | ECS container instance에 적용되는 보안 그룹 |

## 4. Application Load Balancer Security Group 생성

ALB가 인터넷에서 HTTP 요청을 받을 수 있도록 보안 그룹을 먼저 만든다.

1. EC2 콘솔 왼쪽 메뉴에서 **Security Groups** 클릭
2. **Create security group** 클릭
3. 설정값 입력
    - Security group name: `week9-ecs-ec2-alb-sg`
    - VPC: Default VPC
4. Inbound rule:

```text
Type: HTTP
Port: 80
Source: 0.0.0.0/0
```

5. **Create security group** 클릭

## 5. ECS EC2 Security Group 수정

ECS EC2 instance는 ALB에서 오는 요청만 받도록 설정한다.

1. EC2 콘솔 왼쪽 메뉴에서 **Security Groups** 클릭
2. `week9-ecs-ec2-sg` 선택
3. **Inbound rules** → **Edit inbound rules** 클릭
4. Inbound rule:

```text
Type: Custom TCP
Port range: 32768-61000
Source: week9-ecs-ec2-alb-sg
```

> [!NOTE]
> `bridge` network mode에서 host port를 `0`으로 설정하면 ECS가 EC2 instance의 임시 port를 자동으로 할당한다. 그래서 ALB가 EC2의 `32768-61000` 범위 port로 접근할 수 있어야 한다.

## 6. Target Group 생성

1. EC2 콘솔 왼쪽 메뉴에서 **Target Groups** 클릭
2. **Create target group** 클릭
3. 설정값 입력
    - Choose a target type: `Instances`
    - Target group name: `week9-ecs-ec2-tg`
    - Protocol: `HTTP`
    - Port: `80`
    - VPC: Default VPC
    - Health check path: `/`
4. **Next** 클릭
5. Register targets 화면에서는 아무것도 등록하지 않는다.
6. **Create target group** 클릭

### 6-1. Target Group에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Target type | `Instances` | ALB가 EC2 instance를 대상으로 요청 전달 |
| Protocol | `HTTP` | 웹 요청 전달 |
| Port | `80` | ECS Service가 실제 동적 port로 다시 등록함 |
| Health check path | `/` | container 상태 확인 경로 |

## 7. Application Load Balancer 생성

1. EC2 콘솔 왼쪽 메뉴에서 **Load Balancers** 클릭
2. **Create load balancer** 클릭
3. **Application Load Balancer**의 **Create** 클릭
4. 설정값 입력
    - Load balancer name: `week9-ecs-ec2-alb`
    - Scheme: `Internet-facing`
    - IP address type: `IPv4`
    - VPC: Default VPC
    - Mappings: 서로 다른 Availability Zone의 public subnet 2개 선택
5. Security Group 선택
    - Security group: `week9-ecs-ec2-alb-sg`
6. Listener 설정
    - Protocol: `HTTP`
    - Port: `80`
    - Default action: `Forward to week9-ecs-ec2-tg`
7. **Create load balancer** 클릭

### 7-1. ALB에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Scheme | `Internet-facing` | 인터넷에서 접속 가능 |
| Listener | `HTTP:80` | 외부 요청을 받는 입구 |
| Security Group | `week9-ecs-ec2-alb-sg` | HTTP 요청 허용 |
| Target Group | `week9-ecs-ec2-tg` | ECS Service로 요청 전달 |

## 8. ECS Task Definition 생성

1. ECS 콘솔 왼쪽 메뉴에서 **Task definitions** 클릭
2. **Create new task definition** 클릭
3. 설정값 입력
    - Task definition family: `week9-ecs-ec2-task`
    - Launch type: `Amazon EC2 instances`
    - Operating system/Architecture: `Linux/X86_64`
    - Network mode: `bridge`
    - CPU: `.25 vCPU`
    - Memory: `.5 GB`
    - Task role: 비워둠
    - Task execution role: `ecsTaskExecutionRole`
4. Container 설정
    - Name: `week9-ecs-container`
    - Image URI: Level 2에서 새로 push한 ECR image URI
    - Container port: `3000`
    - Host port: `0`
    - Protocol: `TCP`
    - Port name: 비워둠
    - App protocol: `HTTP`
5. **Create** 클릭

### 8-1. Task Definition에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Launch type | `Amazon EC2 instances` | EC2 기반 ECS에서 실행 |
| Operating system/Architecture | `Linux/X86_64` | EC2 instance와 맞는 실행 환경 |
| Network mode | `bridge` | EC2의 Docker bridge network 사용 |
| CPU / Memory | `.25 vCPU` / `.5 GB` | Level 1과 같은 실습용 최소 설정 |
| Container port | `3000` | Node app이 listen하는 port |
| Host port | `0` | ECS가 EC2의 임시 port 자동 할당 |
| App protocol | `HTTP` | ALB가 HTTP 서비스로 인식 |

## 9. ECS Service 생성

1. ECS 콘솔 왼쪽 메뉴에서 **Clusters** 클릭
2. `week9-ecs-ec2-cluster` 클릭
3. **Services** 탭 클릭
4. **Create** 클릭
5. 설정값 입력
    - Compute options: `Launch type`
    - Launch type: `EC2`
    - Application type: `Service`
    - Family: `week9-ecs-ec2-task`
    - Service name: `week9-ecs-ec2-service`
    - Desired tasks: `1`
6. Load balancing 설정
    - Load balancer type: `Application Load Balancer`
    - Load balancer: `week9-ecs-ec2-alb`
    - Container: `week9-ecs-container 3000:0`
    - Listener: `HTTP:80`
    - Target group: `week9-ecs-ec2-tg`
7. **Create** 클릭

### 9-1. ECS Service에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Launch type | `EC2` | EC2 instance 위에서 task 실행 |
| Desired tasks | `1` | container task 1개 유지 |
| Load balancer | `week9-ecs-ec2-alb` | 외부 요청 연결 |
| Target group | `week9-ecs-ec2-tg` | EC2 instance와 동적 port 등록 |

## 10. 배포 확인

ECS Service의 task가 `Running`이 될 때까지 기다린다.

Target Group에서 대상이 등록되었는지 확인한다.

1. EC2 콘솔
2. **Target Groups**
3. `week9-ecs-ec2-tg` 선택
4. **Targets** 탭 확인

정상이라면 EC2 instance가 `healthy` 상태로 보인다.

ALB DNS name을 복사한다.

1. EC2 콘솔
2. **Load Balancers**
3. `week9-ecs-ec2-alb` 선택
4. **DNS name** 복사

cmd에서 확인한다.

```cmd
curl http://{ALB_DNS_NAME}
```

정상 응답:

```json
{"message":"hello ecs ec2","path":"/","container":"week9-level2"}
```

## 11. 실습 질문

아래 질문에 짧게 답한다.

1. ECS Fargate와 ECS EC2 방식의 가장 큰 차이는 무엇인가?
2. ECS EC2 기반 Cluster에서 Auto Scaling Group은 어떤 역할을 하는가?
3. `bridge` network mode에서 host port를 `0`으로 설정하면 어떤 일이 일어나는가?
4. EC2 기반 Target Group type을 `Instances`로 선택하는 이유는 무엇인가?
5. ALB Security Group과 ECS EC2 Security Group은 각각 어떤 inbound rule이 필요한가?
6. ECS Service는 task가 종료되면 어떻게 동작하는가?

## 12. 리소스 정리

아래 순서로 삭제한다.

1. ECS Service 삭제
    - ECS → Clusters → `week9-ecs-ec2-cluster` → Services → `week9-ecs-ec2-service` 삭제
2. ECS Cluster 삭제
    - `week9-ecs-ec2-cluster` 삭제
3. Auto Scaling Group 삭제 여부 확인
    - EC2 → Auto Scaling Groups
    - ECS가 만든 ASG가 남아 있으면 삭제
4. EC2 instance 종료 여부 확인
    - EC2 → Instances
    - 실습용 instance가 남아 있으면 종료
5. Load Balancer 삭제
    - EC2 → Load Balancers → `week9-ecs-ec2-alb` 삭제
6. Target Group 삭제
    - EC2 → Target Groups → `week9-ecs-ec2-tg` 삭제
7. Security Group 삭제
    - `week9-ecs-ec2-alb-sg`
    - `week9-ecs-ec2-sg`
8. ECR Repository 삭제
    - ECR → Repositories → `week9-ecs-ec2-app` 삭제
9. 로컬 Docker image 삭제

```cmd
docker rmi week9-ecs-ec2-app:latest
docker rmi {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week9-ecs-ec2-app:latest
```

> [!IMPORTANT]
> EC2 instance와 Load Balancer는 켜져 있으면 비용이 계속 발생할 수 있다. 실습이 끝나면 꼭 삭제한다.
