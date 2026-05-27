<h1 align="center">Auto Scaling 실습 서버</h1>

<p align="center">
  <code>app.py</code>는 AWS ALB + ASG 실습을 위한 간단한 HTTP 서버입니다.<br>
  Python 표준 라이브러리만 사용하며, 별도 웹 프레임워크 설치 없이 실행할 수 있습니다.
</p>

## 동작 방식

- `GET /health`
  - ALB 헬스 체크용 endpoint입니다.
  - CPU 작업 없이 `200 OK`와 `{"status": "ok"}`를 반환합니다.
- `GET /`
  - 부하 테스트용 endpoint입니다.
  - 요청마다 기본 120ms 동안 CPU 연산을 수행한 뒤 hostname과 CPU 작업 결과를 JSON으로 반환합니다.
- `GET /?work_ms=300`
  - 해당 요청만 기본값 대신 CPU 작업 시간을 300ms로 조절합니다.
  - CPU 작업 시간은 최대 2000ms로 제한됩니다.

## EC2 실행

EC2에서는 기본 포트가 `80`이므로 아래처럼 실행합니다.

```bash
python3 app.py
```

Launch Template의 User data 예시:

```bash
#!/bin/bash
cd /home/ubuntu/app
nohup python3 app.py > app.log 2>&1 &
```

## 부하 테스트 실행

ALB 생성 후 복사한 DNS 이름을 `--host`에 넣어 실행합니다.

```bash
python3 load_test.py --host http://{ALB_DNS}
```

스크립트는 워밍업, 폭증, 정상 복귀, scale-in 관찰 순서로 실행되며 응답 시간과 에러율을 주기적으로 출력합니다.

| 단계 | 시간 | 부하 정도 | 내용 |
| --- | --- | --- | --- |
| 워밍업 | 2분 | 동시 요청 5개, 요청당 CPU 작업 120ms | 낮은 부하로 시작해 ALB와 서버 응답이 정상인지 확인합니다. |
| 폭증 | 5분 | 동시 요청 80개, 요청당 CPU 작업 300ms | 높은 부하를 발생시켜 ASG의 scale-out을 유도합니다. |
| 정상 복귀 | 2분 | 동시 요청 5개, 요청당 CPU 작업 120ms | 요청 강도를 워밍업 수준으로 낮춰 서버가 안정 상태로 돌아가는지 확인합니다. |
| scale-in 관찰 | 5분 | 요청 없음 | 요청을 보내지 않고 서버 수가 다시 줄어드는지 관찰합니다. |

## 부하 조절 기준

ASG scaling policy가 평균 CPU 사용률을 기준으로 동작하므로, CPU가 충분히 오르지 않으면 `work_ms` 값을 높입니다.

```bash
python3 load_test.py --host http://{ALB_DNS} --work-ms 500
```
