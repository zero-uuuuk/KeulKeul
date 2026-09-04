# Week 9 Level 2: ECS EC2 기반 배포

Level 2용 Docker image를 새로 만들고, ECS EC2 기반 Cluster에서 실행한 뒤 Application Load Balancer로 접속한다.

## 파일 구성

```text
.
├── app
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── index.js
│   └── package.json
├── README.md
└── assignment.md
```

## 목표

- Level 2용 Docker image를 새로 build하고 ECR에 push한다.
- ECS Cluster를 EC2 기반으로 생성한다.
- EC2 Auto Scaling Group이 ECS Cluster의 container 실행 공간이 되는 것을 확인한다.
- Task Definition에서 `bridge` network mode와 동적 포트 매핑을 사용한다.
- ALB Target Group이 EC2 instance를 대상으로 등록하는 것을 확인한다.
