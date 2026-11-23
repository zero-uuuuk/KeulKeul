# Week 17: ALB + Fargate로 보는 연쇄 장애

2026.11 Microsoft Outlook 장애를 계기로, 서버 몇 대의 이탈이 헬스체크와 자동 교체를 거쳐 전체 장애로 번지는 **연쇄 장애(Cascading Failure)** 를 ALB + ECS Fargate로 재현하고 대응한다.

핵심 흐름:

```text
task 3개 + 지속 부하 (평상시)
-> task 2개 중지 (서버 이탈)
-> 남은 task에 부하 집중 -> 헬스체크 실패 -> 교체 반복 (연쇄 장애)
-> 용량 확보 / 트래픽 차단 (복구)
-> 헬스체크 설정 비교 -> 장애 보고서
```

```text
week17-alb-fargate/
├── README.md
├── presentation.md       # 발표 자료 (개념, 사례)
├── presentation.pptx
├── assignment.md         # 실습 안내
├── app/                  # 요청마다 CPU를 쓰는 Node 서버
└── load/
    └── load.js           # 부하 도구 (초당 요청 수 고정, 1초마다 결과 출력)
```

week9 `level1-ecs-fargate-deploy`의 ECR, ALB, ECS 구성을 그대로 사용한다. 자세한 진행은 `assignment.md`를 따른다.
