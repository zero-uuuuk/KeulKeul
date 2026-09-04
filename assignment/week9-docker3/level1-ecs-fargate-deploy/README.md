# Level 1: ECS Fargate로 Docker Image 배포

`app` 폴더의 Node 서버를 Docker image로 만들고, ECR에 push한 뒤 ECS Fargate Service로 배포한다.

핵심 흐름:

```text
Node app
-> Docker image build
-> ECR repository push
-> ECS task definition
-> ECS cluster/service
-> Application Load Balancer DNS로 접속
```

자세한 진행은 `assignment.md`를 따른다.

