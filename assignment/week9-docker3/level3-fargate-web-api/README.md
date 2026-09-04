# Week 9 Level 3: ECS Fargate Web + API 배포

Web container와 API container를 각각 ECR에 올리고, ECS Fargate Service 2개로 실행한 뒤 ALB path routing으로 연결한다.

## 파일 구성

```text
.
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
