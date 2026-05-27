## Assignment: 트래픽 변화에 따라 자동 확장되는 웹 서버

간단한 HTTP 서버를 ALB + ASG로 띄우고, 부하 테스트로 Auto Scaling이 실제로 동작하는 걸 시각화한다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한 (EC2, ALB, ASG, CloudWatch)
- 제공된 웹 서버 코드
- 제공된 부하 테스트 스크립트 (Python)

## 1. 인프라 구성 (AWS 콘솔)

아래 순서대로 구성한다. 순서를 지키지 않으면 연결이 안 되는 경우가 많다.

### 1-1. AMI 준비 (EC2 → Instances)

웹 서버가 설치된 EC2 인스턴스를 만들고 AMI로 저장한다. 이후 ASG가 이 AMI로 서버를 찍어낸다.

1. EC2 콘솔 → **Launch Instance**
    - AMI: Ubuntu Server 22.04 LTS
    - 인스턴스 타입: `t3.micro`
    - 키페어: 기존 키페어 선택 또는 새로 생성
    - 보안 그룹: 인바운드 HTTP(80), SSH(22)를 **내 IP에서만** 허용
    - **Advanced details** → **User data**:
    
    ```bash
    #!/bin/bash
    set -eux
    
    # 웹 코드를 GitHub에서 내려받고 Python 서버를 실행하기 위한 패키지만 설치한다.
    apt-get update -y
    apt-get install -y git python3
    
    # 실습 repository와 웹 서버가 위치한 디렉토리를 정의한다.
    REPO_URL=https://github.com/zero-uuuuk/KeulKeul.git
    REPO_BRANCH=feat/week1
    REPO_DIR=/home/ubuntu/KeulKeul
    APP_DIR=$REPO_DIR/assignment/week1-auto-scaling-load-balancer
    
    # 기존 디렉토리가 있으면 제거하고 최신 코드를 얕은 clone으로 내려받는다.
    rm -rf "$REPO_DIR"
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
    chown -R ubuntu:ubuntu "$REPO_DIR"
    
    # 80번 포트로 웹 서버를 백그라운드 실행하고 로그를 파일에 남긴다.
    cd "$APP_DIR"
    nohup python3 app.py > app.log 2>&1 &
    ```
    
    - User data 실행 전, `app.py`가 GitHub repository에 push되어 있어야 한다.
    
2. 로컬 터미널에서 EC2 Public IPv4 주소로 웹 서버 응답 확인
    
    ```bash
    curl http://{EC2_PUBLIC_IP}/health
    curl http://{EC2_PUBLIC_IP}/
    ```
    
3. 인스턴스 선택 → **Actions → Image and templates → Create image**
    - Image name 입력 후 생성
    - EC2 콘솔 → AMIs에서 `available` 상태가 될 때까지 대기

### 1-2. Target Group 생성 (EC2 → Target Groups)

ALB가 트래픽을 보낼 대상 그룹. 헬스 체크 설정이 여기에 있다.

1. **Create target group** 클릭
2. 설정값:
    - Target type: `Instances`
    - Protocol: `HTTP`, Port: `80` (웹 서버 포트에 맞게)
    - VPC: 사용할 VPC 선택
3. **Health checks** 설정:
    - Health check protocol: `HTTP`
    - Health check path: `/health`
    - **Advanced health check settings** 펼치기:
        - Healthy threshold: `2`
        - Unhealthy threshold: `2`
        - Timeout: `5`초
        - Interval: `30`초
        - Success codes: `200`
4. **Next** → 인스턴스 등록 없이 **Create target group**

### 1-3. ALB 생성 (EC2 → Load Balancers)

1. **Create load balancer** → **Application Load Balancer** 선택
2. 기본 설정:
    - Name: 적절한 이름 입력
    - Scheme: `Internet-facing`
    - IP address type: `IPv4`
3. Network mapping:
    - VPC 선택
    - **Availability Zones**: 최소 2개의 AZ 선택, 각각 퍼블릭 서브넷 지정
4. Security groups:
    - 인바운드 HTTP(80) 허용하는 보안 그룹 선택 또는 생성
5. Listeners and routing:
    - Protocol: `HTTP`, Port: `80`
    - Default action: 1-2에서 만든 Target Group 선택
6. **Create load balancer**
7. 생성 완료 후 ALB의 **DNS name** 복사해두기 (부하 테스트에 사용)

### 1-4. Launch Template 생성 (EC2 → Launch Templates)

ASG가 새 서버를 띄울 때 사용할 템플릿.

1. **Create launch template** 클릭
2. 설정값:
    - Launch template name: 적절한 이름 입력
    - **My AMIs** → 1-1에서 만든 AMI 선택
    - Instance type: `t3.micro`
    - Key pair: 기존 키페어 선택
    - Security groups: EC2용 보안 그룹 선택 (인바운드: ALB 보안 그룹에서 오는 HTTP 허용)
3. **Advanced details** → User data:
    - 웹 서버를 자동으로 실행하는 스크립트 입력
    
    ```bash
    #!/bin/bash
    set -eux
    
    # AMI에 포함된 repository 경로에서 웹 서버 디렉토리로 이동한다.
    APP_DIR=/home/ubuntu/KeulKeul/assignment/week1-auto-scaling-load-balancer
    cd "$APP_DIR"
    
    # ASG가 새 인스턴스를 띄울 때마다 80번 포트로 웹 서버를 백그라운드 실행한다.
    nohup python3 app.py > app.log 2>&1 &
    ```
    
4. **Create launch template**

### 1-5. Auto Scaling Group 생성 (EC2 → Auto Scaling Groups)

1. **Create Auto Scaling group** 클릭
2. **Step 1 - Choose launch template**:
    - Name: 적절한 이름 입력
    - Launch template: 1-4에서 만든 템플릿 선택
3. **Step 2 - Choose instance launch options**:
    - VPC 선택
    - Availability Zones: 최소 2개 AZ의 퍼블릭 서브넷 선택
4. **Step 3 - Configure advanced options**:
    - Load balancing: **Attach to an existing load balancer** 선택
    - Target groups: 1-2에서 만든 Target Group 선택
    - Health checks: **Turn on Elastic Load Balancing health checks** 체크
    - Health check grace period: `120`초
5. **Step 4 - Configure group size and scaling**:
    - Desired capacity: `2`
    - Minimum capacity: `2`
    - Maximum capacity: `5`
    - Automatic scaling: **Target tracking scaling policy** 선택
        - Scaling policy name: 적절한 이름 입력
        - Metric type: `Average CPU Utilization`
        - Target value: `50`
        - Instance warmup: `300`초
6. **Step 5, 6**: 기본값 유지
7. **Create Auto Scaling group**

구성 완료 후 확인할 것:

- ASG 콘솔 → **Instance management** 탭에서 인스턴스 2대가 `InService` 상태인지 확인
- EC2 콘솔 → **Target Groups** → 해당 Target Group → **Targets** 탭에서 2대가 `healthy` 상태인지 확인 (최대 2분 소요)
- 브라우저 또는 터미널에서 ALB DNS로 응답 확인:
    
    ```bash
    curl http://{ALB_DNS}/# Hello from {hostname} 응답 확인
    ```
    

## 2. 부하 테스트

제공된 Python 스크립트를 실행한다. `ALB_DNS`를 실제 ALB 주소로 교체한다.

```bash
python3 load_test.py --host http://{ALB_DNS}
```

스크립트는 아래 순서로 부하를 준다.

| 구간 | 시간 | 내용 |
| --- | --- | --- |
| 워밍업 | 2분 | 낮은 부하로 시작 |
| 폭증 | 5분 | 부하를 급격히 높여 스케일링 유도 |
| 정상 복귀 | 2분 | 부하를 낮춤 |
| scale-in 관찰 | 5분 | 서버 수가 줄어드는지 관찰 |

실행 중 확인할 것:

- 터미널에서 응답 시간과 에러율을 실시간으로 관찰한다.
- **스케일링이 일어나지 않으면**: CPU가 50%를 넘지 않는 것이 원인일 가능성이 높다. 스크립트의 동시 요청 수를 높여 재실행한다.
- 부하 테스트는 반드시 ALB DNS 주소로 실행한다. EC2 인스턴스에 직접 요청하면 LB를 거치지 않아 스케일링이 관찰되지 않는다.

## 3. 시각화 (CloudWatch)

부하 테스트 실행 중, 그리고 완료 후 CloudWatch에서 아래를 캡처한다.

### 3-1. ASG 지표 확인

CloudWatch 콘솔 → **Metrics** → **Auto Scaling** → 해당 ASG 선택

아래 두 지표를 같은 그래프에 추가한다.

- `GroupDesiredCapacity` — ASG가 목표로 하는 서버 수
- `GroupInServiceInstances` — 실제로 트래픽을 받는 서버 수

설정:

- 기간(Period): `1분`
- 통계: `Average`
- 시간 범위: 부하 테스트 시작 10분 전 ~ 종료 10분 후

**정상적으로 스케일링이 일어났다면** 그래프에서 아래 흐름이 보여야 한다.

- 부하 전: `GroupInServiceInstances = 2`
- 폭증 구간: `GroupDesiredCapacity`가 올라가고, 잠시 후 `GroupInServiceInstances`가 따라 올라감
- 정상 복귀 후: 두 값이 다시 `2`로 내려옴

### 3-2. ALB 지표 확인

CloudWatch 콘솔 → **Metrics** → **ApplicationELB** → 해당 ALB 선택

아래 지표를 확인한다.

- `TargetResponseTime` — 서버 응답 시간
    - 통계: `p95` (상위 5% 느린 요청의 응답 시간)
    - 폭증 구간에서 올랐다가 새 서버가 투입되면서 내려오는 흐름을 확인
- `HTTPCode_Target_5XX_Count` — 서버 측 에러 수
    - 통계: `Sum`
    - 스케일링이 늦는 구간에 5xx가 얼마나 발생했는지 확인
- `HealthyHostCount` — LB 기준으로 healthy한 서버 수
    - 통계: `Average`
    - ASG의 `GroupInServiceInstances`와 비교해서 같은 시점에 올라가는지 확인

설정:

- 기간(Period): `1분`
- 시간 범위: ASG 지표와 동일하게 맞추기

### 3-3. 캡처 기준

아래 세 구간이 모두 한 화면에 들어오도록 시간 범위를 조정한다.

1. **정상 구간** — 부하 전, 서버 2대가 안정적으로 동작
2. **스케일 아웃 구간** — `GroupDesiredCapacity` 상승 → `GroupInServiceInstances` 상승 → `TargetResponseTime` 회복
3. **스케일 인 구간** — 부하 감소 후 서버 수가 다시 2로 내려오는 시점

`GroupDesiredCapacity`와 `GroupInServiceInstances`가 2 → N → 2로 변하는 흐름이 캡처에 보여야 한다.

## 4. 제출물

1. **인프라 구성 완료 스크린샷** — Target Group의 Targets 탭에서 인스턴스 2대가 `healthy` 상태인 화면
2. **CloudWatch 스크린샷** — 3번 기준을 충족하는 캡처 1장 이상

## 5. 주의사항

과제 완료 후 반드시 아래 순서로 리소스를 삭제한다. 방치하면 비용이 계속 발생한다.

1. **ASG 삭제** — ASG 콘솔 → 해당 ASG 선택 → Delete
2. **ALB 삭제** — Load Balancers → 해당 ALB 선택 → Delete
3. **Target Group 삭제** — Target Groups → 해당 TG 선택 → Delete
4. **Launch Template 삭제** — Launch Templates → 해당 템플릿 선택 → Delete
5. **AMI 등록 취소 및 스냅샷 삭제** — AMIs → Deregister → 연결된 Snapshot도 삭제
6. **EC2 인스턴스 종료** — Instances → Terminate
