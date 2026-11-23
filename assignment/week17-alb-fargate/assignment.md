# Assignment: ALB + Fargate로 연쇄 장애 재현하고 대응하기

ECS Fargate task 3개를 ALB 뒤에 두고 계속 부하를 건 상태에서 task 2개를 중지한다. 남은 task에 부하가 몰리고, 헬스체크 실패로 task가 계속 교체되는 **연쇄 장애**를 관찰한 뒤 복구하고, 헬스체크 설정에 따라 결과가 어떻게 달라지는지 비교한다.

2026.11 Microsoft Outlook 장애의 흐름(서버 일부 이탈 → 부하 집중 → 헬스체크 실패 → 악순환)을 작게 재현하는 실습이다. 개념은 `presentation.md`를 참고한다.

참고 자료:
- https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/load-balancer-healthcheck.html

> [!IMPORTANT]
> ECS와 Load Balancer는 비용이 발생할 수 있다. 실습 후 반드시 리소스를 삭제한다.

## 0. 사전 준비

- week9 `level1-ecs-fargate-deploy` 완료 권장 (ECR push, ALB, ECS Service 생성 과정을 이번 실습에서는 짧게 다룬다)
- Docker Desktop, Node.js, AWS CLI
- 실습 리전: `ap-northeast-2`
- 제공 파일
  - `app`: 요청마다 CPU를 쓰는 Node 서버
  - `load/load.js`: 초당 정해진 개수의 요청을 보내고 결과를 1초마다 출력하는 부하 도구

### 0-1. 실습 화면 배치

장애 대응은 **여러 곳을 동시에 보면서 판단**하는 일이다. 아래 4개 화면을 띄워 두고 진행한다.

| 화면 | 역할 |
| --- | --- |
| 터미널 1 | `load.js` 실행. **사용자가 겪는 성공·실패**를 보는 창 |
| 터미널 2 | AWS CLI로 장애 유발·복구 조작 |
| 브라우저 탭 A | EC2 → Target Groups → `week17-tg` → **Targets** 탭 (healthy / unhealthy / draining) |
| 브라우저 탭 B | ECS → Clusters → `week17-cluster` → Services → `week17-service` → **Events** 탭 (task 중지·시작 기록) |

## 1. 앱과 부하 도구 로컬 확인

터미널 1에서 서버를 실행한다.

```cmd
cd /d "{ASSIGNMENT_PATH}\week17-alb-fargate\app"
npm start
```

터미널 2에서 확인한다.

```cmd
curl http://localhost:3000
curl http://localhost:3000/health
```

정상 응답:

```text
{"message":"hello","task":"{컴퓨터 이름}","cpu_ms":...,"capacity_rps":...}
ok
```

터미널 2에서 부하 도구를 실행한다.

```cmd
cd /d "{ASSIGNMENT_PATH}\week17-alb-fargate\load"
node load.js http://localhost:3000 5
```

출력 예:

```text
17:56:17  보냄 5  성공 5  실패 0  평균 19ms  task 1개 처리량≈110rps  | DESKTOP-ABC:5
```

| 항목 | 의미 |
| --- | --- |
| 보냄 | 이번 1초 동안 보낸 요청 수. **응답을 기다리지 않고 일정하게 보낸다** (사용자는 서버 사정을 봐주지 않는다) |
| 성공 / 실패 | 이번 1초 동안 끝난 요청 결과. 실패는 `503`, `502`, `timeout`(5초 초과), `연결실패`로 나눠 표시 |
| 평균 | 성공한 요청의 평균 응답 시간 |
| task 1개 처리량 | 서버가 측정한 CPU 사용량으로 계산한, **0.25 vCPU task 1개가 1초에 처리할 수 있는 요청 수** |
| `| 이름:숫자` | 어떤 task가 몇 개를 응답했는지 |

두 터미널 모두 `Ctrl + C`로 종료한다.

> [!NOTE]
> Windows에서는 CPU 측정 단위가 거칠어서 로컬의 `처리량` 값이 들쭉날쭉할 수 있다. Fargate(Linux)에서는 안정적으로 나온다.

### 1-1. 앱에서 확인할 항목

| 경로 | 동작 | 역할 |
| --- | --- | --- |
| `/` | 요청마다 `pbkdf2` 해시 계산으로 CPU 사용 | HTTPS 연결 처리(TLS handshake)처럼 CPU를 쓰는 요청 |
| `/health` | 바로 `ok` 응답 | ALB 헬스체크 경로 |

`/health`는 가볍지만, Node 서버는 한 번에 하나씩 처리한다. **CPU가 밀리면 헬스체크 요청도 같이 밀린다.** 이게 이번 실습의 핵심이다.

## 2. Docker image를 ECR에 push

week9 level1의 2~4단계와 같다. 이름만 바꾼다.

1. ECR에서 `week17-app` repository 생성 (Private, Mutable)
2. 아래 명령어 실행 (`{ACCOUNT_ID}`는 본인 계정 ID)

```cmd
cd /d "{ASSIGNMENT_PATH}\week17-alb-fargate\app"
docker build -t week17-app .
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com
docker tag week17-app:latest {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week17-app:latest
docker push {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week17-app:latest
```

> [!IMPORTANT]
> Mac(Apple Silicon)에서는 `docker build --platform linux/amd64 -t week17-app .`로 build한다.

## 3. AWS 리소스 생성

Target Group → ALB → Task Definition → Cluster → Service 순서로 만든다. 표에 없는 항목은 기본값을 사용한다.

| 단계 | 항목 | 값 |
| --- | --- | --- |
| **Target Group** | Target type | `IP addresses` |
| | Name | `week17-tg` |
| | Protocol / Port | `HTTP` / `3000` |
| | VPC | Default VPC |
| | Health check path | `/health` |
| | Advanced health check settings → Healthy threshold | `2` |
| | Unhealthy threshold | `2` |
| | Timeout | `2` |
| | Interval | `5` |
| | Register targets | 아무것도 등록하지 않음 |
| **ALB** | Name | `week17-alb` |
| | Scheme / IP address type | `Internet-facing` / `IPv4` |
| | Mappings | Default VPC, 서로 다른 AZ의 public subnet 2개 |
| | Security group | 새로 생성 `week17-alb-sg` (inbound HTTP 80, Source `0.0.0.0/0`) |
| | Listener / Default action | `HTTP:80` / `Forward to week17-tg` |
| **Task Definition** | Family | `week17-task` |
| | Launch type / OS·Architecture | `AWS Fargate` / `Linux/X86_64` |
| | CPU / Memory | `.25 vCPU` / `.5 GB` |
| | Task execution role | `ecsTaskExecutionRole` |
| | Container name | `week17-container` |
| | Image URI | 2단계에서 push한 `week17-app` image URI |
| | Container port / Protocol | `3000` / `TCP` |
| | Environment variables | Key `WORK`, Value `30000` |
| **Cluster** | Name / Infrastructure | `week17-cluster` / `AWS Fargate` |
| **Service** | Compute options / Launch type | `Launch type` / `FARGATE` |
| | Family | `week17-task` |
| | Service name | `week17-service` |
| | Desired tasks | **`3`** |
| | Health check grace period | **`0`** |
| | VPC / Subnets | Default VPC / public subnet 2개 |
| | Security group | 새로 생성 `week17-service-sg` (inbound Custom TCP 3000, Source `week17-alb-sg`) |
| | Public IP | `Turned on` |
| | Load balancer | `week17-alb`, Container `week17-container 3000:3000`, Listener `HTTP:80`, Target group `week17-tg` |

Target Group을 만든 뒤 **Deregistration delay**도 바꾼다.

1. EC2 → Target Groups → `week17-tg` → **Attributes** 탭 → **Edit**
2. Deregistration delay: `5` seconds
3. **Save changes**

### 3-1. 왜 이 값으로 설정하는가

| 설정 | 값 | 이유 |
| --- | --- | --- |
| Interval / Timeout | 5초 / 2초 | 2초 안에 응답 못 하면 실패. **느릴 뿐인 서버도 실패로 판정**된다 |
| Unhealthy threshold | 2 | 2번(약 10초) 연속 실패하면 unhealthy |
| Health check grace period | 0 | 새 task도 시작하자마자 헬스체크 결과로 판정받는다 |
| Deregistration delay | 5초 | 기본값 300초면 빠진 task가 5분 동안 draining 상태로 남아 관찰이 늦어진다 |
| Desired tasks | 3 | 2개를 빼도 1개가 남는 구성 |

> [!NOTE]
> 이 설정은 장애를 **잘 보이게** 하려고 일부러 빡빡하게 잡은 값이다. 운영 환경 권장값이 아니다. 7단계에서 느슨한 설정과 비교한다.

## 4. 평상시 상태 확인과 부하 맞추기

ECS Service의 task 3개가 `Running`, 탭 A에서 target 3개가 `healthy`가 될 때까지 기다린다.

ALB DNS name을 복사한다. (EC2 → Load Balancers → `week17-alb` → DNS name)

### 4-1. task 1개 처리량 확인

터미널 1에서 약하게 부하를 건다.

```cmd
cd /d "{ASSIGNMENT_PATH}\week17-alb-fargate\load"
node load.js http://{ALB_DNS_NAME} 2
```

10초 정도 지켜보고 `task 1개 처리량≈Nrps`의 N 값을 적는다. `Ctrl + C`로 종료한다.

### 4-2. 실습용 부하 걸기

**RPS = N × 2** 로 정한다. (예: N이 15면 RPS는 30)

| 상황 | task당 부하 |
| --- | --- |
| task 3개 | 약 67% → 여유 있게 처리 |
| task 1개 | 약 200% → 처리 불가 |

터미널 1에서 실행하고, **실습이 끝날 때까지 끄지 않는다.**

```cmd
node load.js http://{ALB_DNS_NAME} {RPS}
```

확인할 것:

- 실패가 0인가?
- `|` 뒤에 task 3개가 비슷한 개수로 나오는가?
- 탭 A에서 target 3개가 모두 `healthy`인가?

> [!NOTE]
> 실패가 계속 나오면 RPS를 줄이고, 평균 응답 시간이 수십 ms로 아주 여유 있으면 조금 늘린다. 목표는 **3개일 때는 실패 0, 평균 응답 시간이 안정적인 상태**다.

## 5. 장애 유발: 서버 2대 이탈

Outlook 장애의 "네트워크 변경으로 서버 일부가 사용 불가" 상황을 task 2개 중지로 재현한다.

### 5-1. 준비

터미널 2에서 실행 중인 task 목록을 확인한다.

```cmd
aws ecs list-tasks --region ap-northeast-2 --cluster week17-cluster --service-name week17-service
```

출력된 `taskArns` 중 **2개**를 메모장에 복사해 두고, 아래 명령어 2줄을 미리 만들어 둔다.

```cmd
aws ecs stop-task --region ap-northeast-2 --cluster week17-cluster --reason "simulated outage" --task {TASK_ARN_1}
aws ecs stop-task --region ap-northeast-2 --cluster week17-cluster --reason "simulated outage" --task {TASK_ARN_2}
```

### 5-2. 실행

시각을 적어 두고, 두 명령어를 **연달아** 실행한다.

### 5-3. 관찰 (3~5분)

| 시점 | 터미널 1 (`load.js`) | 탭 A (Targets) | 탭 B (Events) |
| --- | --- | --- | --- |
| 중지 직후 | task 1개만 응답, 평균 응답 시간 증가 | 2개 `draining` | 2개 task stopped |
| 수십 초 후 | 응답 시간이 수 초로 증가, `timeout` 발생 | 남은 1개 `unhealthy` | unhealthy task 중지, 새 task 시작 |
| 이후 | `503`, `502`, `timeout`이 섞여 반복 | 새 target이 `initial` → `unhealthy`를 반복 | task 시작·중지가 계속 반복 |

> [!NOTE]
> 실제 결과는 RPS, task 시작 시각에 따라 다를 수 있다. **위 표와 다르게 나온 부분**도 그대로 기록한다. 장애 대응에서는 예상과 다른 현상이 가장 중요한 단서다.

> [!NOTE]
> ALB는 target이 **모두** unhealthy가 되면 오히려 모든 target에 요청을 보낸다(fail-open). 그래서 "전부 503"이 아니라 느린 성공, `timeout`, `502`가 섞여 나올 수 있다.

### 5-4. 판단 질문

조치하기 전에 아래 질문에 먼저 답한다.

1. 터미널 1의 `보냄` 숫자는 장애 전후로 달라졌는가? → **트래픽이 늘어서** 생긴 장애인가, **서버가 줄어서** 생긴 장애인가?
2. 남은 task는 실제로 고장 났는가, 아니면 **느렸을 뿐**인가? 어떤 화면에서 알 수 있는가?
3. ECS는 unhealthy task를 새 task로 교체했다. 이 동작은 상황을 좋게 만들었는가, 나쁘게 만들었는가?
4. task 2개만 중지했는데 왜 3개 모두가 영향을 받았는가?

## 6. 복구

### 6-1. 용량 늘리기 (부하는 그대로 유지)

실제 서비스에서는 사용자 요청을 멈출 수 없다. **부하를 유지한 채로** 터미널 2에서 task 수를 늘린다.

```cmd
aws ecs update-service --region ap-northeast-2 --cluster week17-cluster --service week17-service --desired-count 6
```

2~3분 관찰한다.

확인할 것:

- 실패가 줄어드는가?
- 탭 A에서 `healthy` target이 늘어나는가?
- 복구되기까지 몇 분 걸렸는가?

### 6-2. 그래도 복구되지 않으면: 트래픽 차단

터미널 1에서 `Ctrl + C`로 부하를 멈춘다. Outlook 장애에서 부하를 재분배하고 변경을 되돌린 것처럼, **먼저 악순환을 끊는** 조치다.

탭 A에서 target이 모두 `healthy`가 되면 같은 RPS로 부하를 다시 건다.

```cmd
node load.js http://{ALB_DNS_NAME} {RPS}
```

### 6-3. 원래대로 돌리기

실패가 0이 된 것을 확인하고 task 수를 3으로 되돌린다.

```cmd
aws ecs update-service --region ap-northeast-2 --cluster week17-cluster --service week17-service --desired-count 3
```

target 3개가 `healthy`, 실패 0인 상태가 될 때까지 기다린다.

## 7. 비교 실험: 헬스체크를 느슨하게

같은 장애를 헬스체크 설정만 바꿔서 다시 낸다.

1. EC2 → Target Groups → `week17-tg` → **Health checks** 탭 → **Edit**
2. 값 변경

| 항목 | 5단계 (빡빡함) | **7단계 (느슨함)** |
| --- | --- | --- |
| Interval | 5 | `30` |
| Timeout | 2 | `10` |
| Unhealthy threshold | 2 | `5` |

3. **Save changes**
4. 터미널 1의 부하가 실행 중이고 실패 0인지 확인
5. 5-1, 5-2와 같은 방법으로 task 2개 중지
6. 3~5분 관찰

### 7-1. 비교

| 항목 | 빡빡한 헬스체크 | 느슨한 헬스체크 |
| --- | --- | --- |
| 남은 task가 unhealthy가 되었는가? | | |
| task 교체가 반복되었는가? | | |
| 주로 나온 실패 종류 | | |
| 스스로 복구되었는가? 몇 분 걸렸는가? | | |

### 7-2. 생각해 볼 것

느슨한 헬스체크가 항상 좋은 것은 아니다.

- 정말로 죽은 서버를 찾아내는 데는 얼마나 걸리는가? (Interval × Unhealthy threshold)
- 그동안 그 서버로 간 요청은 어떻게 되는가?

헬스체크는 **너무 빡빡하면 느린 서버를 죽이고, 너무 느슨하면 죽은 서버를 늦게 뺀다.** 정답 값은 없고, 서비스 특성에 맞게 정해야 한다.

## 8. 장애 보고서 쓰기

실제 회사들은 장애가 끝나면 사후 보고서(Postmortem)를 쓴다. 5~6단계의 장애를 아래 양식으로 정리한다.

```text
## 장애 보고서

### 요약
(한두 문장: 언제, 무엇이, 얼마나 영향을 받았나)

### 타임라인
| 시각 | 일어난 일 |
| --- | --- |
| HH:MM | task 2개 중지 |
| HH:MM | 첫 timeout 발생 |
| HH:MM | 남은 task unhealthy |
| HH:MM | desired 6으로 변경 |
| HH:MM | 실패 0 회복 |

### 원인
- 계기:
- 장애를 키운 것:

### 영향
- 장애 시간:
- 실패한 요청 종류:

### 재발 방지
- (발표자료 6. 대응·예방 패턴 중 이번 장애에 맞는 것 2개 이상)
```

## 9. 실습 질문

1. 처음 장애 원인은 task 2개 중지였다. 그런데 장애를 **키운** 것은 무엇이었는가?
2. 헬스체크 경로 `/health`는 아무 일도 하지 않는데 왜 실패했는가?
3. Desired tasks를 3이 아니라 처음부터 4로 했다면 결과가 어떻게 달라졌을까? (N+1 용량 여유)
4. `load.js`가 timeout 후 바로 재시도했다면 장애는 어떻게 되었을까?
5. Microsoft Outlook 장애와 이번 실습에서 같은 점과 다른 점은 무엇인가?

## 10. 리소스 정리

아래 순서로 삭제한다.

1. 터미널 1의 `load.js`를 `Ctrl + C`로 종료
2. ECS Service 삭제
    - ECS → Clusters → `week17-cluster` → Services → `week17-service` 삭제
3. ECS Cluster 삭제
    - `week17-cluster`
4. Load Balancer 삭제
    - EC2 → Load Balancers → `week17-alb`
5. Target Group 삭제
    - EC2 → Target Groups → `week17-tg`
6. ECR Repository 삭제
    - ECR → Repositories → `week17-app`
7. Security Group 삭제
    - `week17-alb-sg`
    - `week17-service-sg`
8. 로컬 Docker image 삭제

```cmd
docker rmi week17-app:latest
docker rmi {ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/week17-app:latest
```

> [!IMPORTANT]
> Load Balancer는 켜져 있으면 비용이 계속 발생한다. 이번 실습은 task를 최대 6개까지 늘리므로, 실습이 끝나면 꼭 삭제한다.

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| 4단계에서 target이 `healthy`가 안 됨 | Health check path `/health`, Container port `3000`, `week17-service-sg` inbound |
| 4단계에서 처리량 값이 안 나옴 | 성공한 요청이 있어야 계산된다. ALB DNS와 target 상태 확인 |
| 4단계에서 부하 없이도 실패 | RPS를 낮추고, Task Definition의 `WORK` 값이 `30000`인지 확인 |
| 5단계에서 장애가 안 남 | RPS를 N × 2보다 높여서 다시 시도 |
| 6-1에서 6개로 늘려도 복구 안 됨 | 정상일 수 있다. 6-2 트래픽 차단으로 진행 |
| `stop-task`에서 오류 | Task ARN 전체를 복사했는지, `--cluster week17-cluster`가 맞는지 확인 |
