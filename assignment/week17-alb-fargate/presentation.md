- **이번 스터디에서 알아볼 내용**
    - 2026년 11월 Microsoft Outlook 장애는 왜 일어났는가?
    - 서버 몇 대의 문제가 왜 전체 서비스 장애로 번지는가?
    - 헬스체크·오토스케일링·재시도는 왜 오히려 장애를 키울 수 있는가?
    - 다른 회사에도 비슷한 사례가 있었는가?
    - 연쇄 장애는 어떻게 막고, AWS에서는 어떻게 재현할 수 있는가?

---

# **1. Microsoft Outlook 장애 개요 (2026.11.12)**

**Exchange Online(Outlook 메일 서버)에 접속이 안 되는 문제**가 미주 지역에서 시작되어 Microsoft 365 전반의 성능 저하로 번진 장애

- 인시던트 번호: `EX1550543` (Exchange Online), `MO1550821` (Microsoft 365)
- 사이버 공격의 흔적은 없다고 발표

| 시점 | 내용 |
| --- | --- |
| 11/12 16:17 UTC | 미주 지역에서 Exchange Online 메일함 접속 문제 보고 |
| 이후 | Outlook·Teams 등 Microsoft 365 전반으로 영향 확대 |
| 조사 중 | "부하가 높은 이유는 트래픽 증가가 아니라, **다수의 서버가 예기치 않게 사용 불가가 되어 남은 인프라에 부담이 몰렸기 때문**" |
| 조치 | 최근 네트워크 구성 변경을 되돌리고(revert), 모든 배포를 일시 중지 |
| 11/13 | 점진적 복구 → 서비스 복구 발표 (출처마다 시각이 다름) |

> 💡 Microsoft의 예비 설명: **이전에 진행한 네트워크 용량 업그레이드의 문제가, 최근 네트워크 변경 이후 드러났다.**

⚠️ 최종 사후 보고서(Post-Incident Report)는 아직 공개 전이므로, 아래 분석은 **현재까지 공개된 예비 설명 기준**이다.

---

# **2. 장애 흐름 분석**

> 네트워크 변경 → 일부 서버 이탈 → 남은 서버에 부하 집중 → 보안 연결(TLS) 처리 프로세스 과부하 → 헬스체크 실패 → 서버가 트래픽 대상에서 제외 → 남은 서버에 부하 더 집중 → …
>

!image.png (장애 흐름 순환 그림)

- **시작점**: 트래픽이 늘어난 게 아니다!! 처리할 **서버 수가 줄어든 것**
- **보안 연결 프로세스**: HTTPS 요청은 먼저 TLS handshake로 암호화 연결을 맺어야 한다. 이 과정은 CPU를 많이 쓰기 때문에, 부하가 몰리면 가장 먼저 병목이 된다.
- **헬스체크 실패**: 과부하로 응답이 느려진 서버는 "죽었다"고 판정되어 로드밸런서에서 빠진다.
- **악순환**: 서버가 빠질수록 남은 서버의 부하가 커지고, 그 서버들도 헬스체크에 실패한다.

결국 **처음 원인(네트워크 변경)보다, 그 뒤에 이어진 악순환이 장애를 키웠다.**

---

# **3. 연쇄 장애(Cascading Failure)란?**

**연쇄 장애**는 시스템 일부의 장애가 다른 부분의 부하를 늘리고, 그 부하가 다시 장애를 만드는 **양의 피드백 고리(positive feedback loop)** 로 전체 시스템이 무너지는 현상

> 💡 예: 서버 4대가 각각 70% 부하로 일하는 중 1대가 죽는다
> → 남은 3대가 약 93%씩 부담 → 1대가 더 과부하로 죽는다
> → 남은 2대가 140%씩 부담해야 함 → **전부 다운!!**

| 구분 | 일반 장애 | 연쇄 장애 |
| --- | --- | --- |
| 범위 | 고장 난 부분만 영향 | 정상이던 부분까지 차례로 고장 |
| 원인 | 하나의 결함 | 작은 계기 + 시스템의 반응 |
| 복구 | 고장 부분을 고치면 끝 | 원인을 고쳐도 부하가 계속 몰려 **다시 무너질 수 있음** |

⚠️ 연쇄 장애는 원인을 되돌려도 바로 복구되지 않는 경우가 많다. 다시 띄운 서버가 **쌓여 있던 부하를 한꺼번에 받고** 바로 다시 죽기 때문이다.

---

# **4. 장애를 키우는 장치들**

원래는 **안정성을 위해 넣은 장치**가 연쇄 장애 상황에서는 반대로 작동한다.

| 장치 | 원래 목적 | 연쇄 장애 상황에서의 역효과 |
| --- | --- | --- |
| **헬스체크** | 고장 난 서버를 트래픽에서 제외 | 느릴 뿐인 정상 서버까지 제외 → **용량 감소** |
| **자동 교체 / 재시작** | 고장 난 서버를 새로 띄움 | 새 서버가 준비되기 전에 부하를 받고 다시 실패 → 무한 반복 |
| **오토스케일링** | 부하에 맞춰 서버 수 조절 | 잘못된 지표에 반응하거나, 확장 요청이 몰려 배포 시스템까지 과부하 |
| **재시도(Retry)** | 일시적 실패를 극복 | 모든 클라이언트가 동시에 재시도 → 트래픽이 몇 배로 증폭 (**thundering herd**) |

> 💡 **Thundering herd**: 잠들어 있던 소떼가 한꺼번에 뛰쳐나가듯, 많은 클라이언트가 **같은 순간에** 같은 자원으로 몰리는 현상

!image.png (헬스체크로 서버가 하나씩 빠지는 그림)

---

# **5. 비슷한 사례**

**AWS us-east-1 — DNS 오류 → 헬스체크가 정상 노드까지 제거 (2025.10)**

- DynamoDB DNS 자동화의 경쟁 조건(race condition)으로 엔드포인트의 DNS 레코드가 비어 버림
- 이후 새 EC2 인스턴스가 네트워크 설정이 반영되기 전에 서비스에 투입됨 → **NLB 헬스체크 실패 → 자동 failover가 용량을 제거**
- AWS는 NLB 헬스체크 자동 failover를 **수동으로 꺼서** 악순환을 끊음
- 전체 영향 약 15시간
- **헬스체크 / 자동 교체**

**Slack — 첫 출근일 트래픽 → 오토스케일링 역효과 (2021.01.04)**

- 연휴 후 첫 업무일, 캐시가 비어 있는 클라이언트들이 평소보다 많은 데이터를 요청
- AWS Transit Gateway가 제때 확장되지 못해 패킷 손실 발생
- 패킷 손실로 웹 서버 CPU 사용률이 **오히려 낮아짐** → 오토스케일러가 서버를 **줄임**
- 뒤늦게 서버 1,200대 추가를 시도 → 서버 준비 시스템까지 과부하
- 모니터링도 같은 네트워크를 거쳐서 장애와 함께 먹통
- **오토스케일링 / 모니터링 의존성**

**Microsoft 365 — WAN 라우터 IP 변경 (2023.01.25)**

- 계획된 WAN 라우터 IP 변경 명령 하나로 WAN의 모든 라우터가 라우팅 테이블을 재계산
- Outlook, Teams, SharePoint 등 약 5시간 30분 장애
- WAN 상태를 관리하던 자동화 시스템도 일시 중단되어 복구가 늦어짐
- **네트워크 변경 / 같은 회사의 비슷한 계기**

**Google Cloud — 재시도 폭주로 복구 지연 (2025.06.12)**

- 정책 데이터 변경으로 Service Control(API 요청 인증·할당량 관리) 바이너리가 전 세계에서 크래시
- 재시작된 작업들이 **무작위 지수 백오프 없이** 한꺼번에 Spanner 테이블에 접근 → herd effect
- 다른 리전은 빨리 회복했지만 us-central1은 복구에 훨씬 오래 걸림
- **재시도 / thundering herd**

| 사례 | 계기 | 장애를 키운 장치 |
| --- | --- | --- |
| Microsoft Outlook (2026) | 네트워크 변경 | 헬스체크, 부하 집중 |
| AWS us-east-1 (2025) | DNS 자동화 버그 | 헬스체크 자동 failover |
| Slack (2021) | 트래픽 급증 | 오토스케일링, 모니터링 의존성 |
| Microsoft 365 (2023) | 라우터 명령 | 네트워크 자동 재계산 |
| Google Cloud (2025) | 정책 데이터 변경 | 백오프 없는 재시도 |

→ **회사도 계기도 다르지만, "작은 계기 + 시스템의 자동 반응 = 전체 장애" 패턴은 같다!!**

---

# **6. 대응·예방 패턴**

| 패턴 | 설명 | 막아주는 것 |
| --- | --- | --- |
| **용량 여유 (N+1)** | 서버 1대(또는 AZ 1개)가 빠져도 버틸 수 있게 여유를 둠 | 부하 집중 |
| **지수 백오프 + Jitter** | 재시도 간격을 1s → 2s → 4s…로 늘리고, 무작위 값을 더해 시점을 분산 | 재시도 폭주 |
| **Circuit Breaker** | 실패가 계속되면 일정 시간 요청 자체를 차단 | 죽어가는 서버에 부하 추가 |
| **Load Shedding** | 처리할 수 없는 요청은 빨리 거절(503)하고 처리 가능한 만큼만 받음 | 서버 전체 과부하 |
| **헬스체크 튜닝** | 판정 기준을 너무 빡빡하게 잡지 않음, 전부 unhealthy일 때는 fail-open | 정상 서버의 과도한 제외 |
| **단계적 배포 + 빠른 롤백** | 변경을 일부에만 먼저 적용하고, 문제가 생기면 즉시 되돌림 | 변경으로 인한 전체 영향 |
| **모니터링 분리** | 모니터링은 서비스와 다른 경로·장애 영역에 둠 | 장애 중 상황 파악 불가 |

> 💡 **Fail-open**: AWS ALB는 대상이 **전부** unhealthy가 되면 오히려 모든 대상에 트래픽을 보낸다. "모두 죽었다"는 판정은 헬스체크 쪽이 틀렸을 가능성이 높기 때문!!

⚠️ 장애 직후에는 **변경 중단(배포 freeze)** 이 먼저다. Microsoft도 이번 장애 중 모든 배포를 멈추고 원인을 조사했다.

---

# **7. AWS로 재현하기: ALB + Fargate**

Outlook 장애의 핵심 구조(서버 이탈 → 부하 집중 → 헬스체크 실패 → 악순환)를 작은 규모로 재현할 수 있다.

> 사용자 요청 → **ALB** (헬스체크) → **ECS 서비스 (Fargate task 3개)**
>

!image.png (ALB + Fargate 구성도)

| Outlook 장애 | 재현 환경 |
| --- | --- |
| Exchange Online 서버 | Fargate task (0.25 vCPU) |
| TLS handshake 처리 비용 | 요청마다 CPU를 쓰는 연산 |
| 로드밸런서 헬스체크 | ALB target group 헬스체크 |
| 네트워크 변경으로 서버 이탈 | task 일부를 직접 중지 |
| 서버 자동 교체 | ECS가 unhealthy task를 교체 |
| 변경 되돌리기 / 부하 재분배 | 부하 중단, task 수 늘리기 |

#### 왜 EC2 Auto Scaling Group이 아니라 Fargate인가?

| 항목 | EC2 ASG | Fargate |
| --- | --- | --- |
| 준비 | AMI·user data 필요 | 공개 이미지 + 명령만 지정 (빌드 불필요) |
| 교체 속도 | 인스턴스 교체에 수 분 | task 교체 30~60초 → 실습 시간 안에 관찰 가능 |
| 자동 교체 | 설정 필요 | ECS가 헬스체크 실패 task를 자동 교체 → **악순환이 그대로 보임** |

---

### 참고 자료

- [Microsoft 365 Status (X) — 서버 이탈로 인한 부하 설명](https://x.com/MSFT365Status/status/2120962673911181437)
- [TechRadar — Outlook outage live (2026.11)](https://www.techradar.com/news/live/outlook-outage-nov-2026)
- [SecurityWeek — Microsoft 365 Outage Disrupts Outlook, Exchange Online and Teams](https://www.securityweek.com/microsoft-365-outage-disrupts-outlook-exchange-online-and-teams/)
- [Microsoft 365 outage, 12 November 2026 (azureblog)](https://azureblog.co.uk/posts/microsoft-365-outage-12-november-2026/)
- [More Than DNS: The 14 hour AWS us-east-1 outage](https://thundergolfer.com/blog/aws-us-east-1-outage-oct20)
- [The Register — Slack fingers AWS auto-scaling failure](https://www.theregister.com/2021/02/02/slack_outage_aws_autoscaling/)
- [Slack's Jan 2021 outage: a tale of saturation](https://surfingcomplexity.blog/2021/02/08/slacks-jan-2021-outage-a-tale-of-saturation/)
- [BleepingComputer — Microsoft 365 outage caused by WAN router IP change](https://www.bleepingcomputer.com/news/microsoft/massive-microsoft-365-outage-caused-by-wan-router-ip-change/)
- [Google Cloud Service Health — Incident Report (2025.06.12)](https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW)
