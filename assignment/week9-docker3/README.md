# Week 9: Docker Image를 ECS로 배포하기

이번 주차에서는 Docker image를 AWS ECR에 올리고, ECS Fargate와 ECS EC2 방식으로 실행한 뒤 Application Load Balancer로 외부 접속을 확인한다.

## 파일 구성

```text
.
├── README.md
├── level1-ecs-fargate-deploy
    ├── README.md
    ├── assignment.md
    └── app
        ├── .dockerignore
        ├── Dockerfile
        ├── index.js
        └── package.json
├── level2-ecs-ec2-deploy
    ├── README.md
    └── assignment.md
└── level3-fargate-web-api
    ├── README.md
    ├── assignment.md
    ├── api
    │   ├── .dockerignore
    │   ├── Dockerfile
    │   ├── index.js
    │   └── package.json
    └── web
        ├── .dockerignore
        ├── Dockerfile
        ├── index.html
        └── nginx.conf
```

## Level

| Level | 주제 | 목표 |
| --- | --- | --- |
| Level 1 | ECS Fargate 배포 | Docker image를 ECR에 push하고 ECS Service + ALB로 접속 확인 |
| Level 2 | ECS EC2 기반 배포 | EC2 기반 ECS Cluster에서 Docker container 실행 |
| Level 3 | Fargate Web + API 배포 | ALB path routing으로 web과 api service 분리 |
