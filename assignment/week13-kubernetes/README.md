# Week 13: Kubernetes

Minikube 준비 → 웹 서버 Pod 3개 배포 → Service 부하분산·Pod 자가복구 → 이미지 업데이트·롤백 → 리소스 정리 순서로 진행한다.

**[전체 실습 안내](practice.md)** · 설치와 다운로드를 제외하고 약 30~45분 예상.

```text
week13-kubernetes/
├── README.md
└── practice.md          # Windows / Mac 통합 실습
```

Google hello-app 샘플 이미지 1.0과 2.0을 사용한다. 앱 코드 수정이나 이미지 빌드 없이 문서의 명령으로 실습한다.
