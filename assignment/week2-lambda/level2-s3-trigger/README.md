<h1 align="center">Lambda S3 Trigger 실습</h1>

<p align="center">
  <code>lambda_function.py</code>는 S3 버킷에 파일이 업로드될 때 자동 실행되는 Lambda 코드입니다.<br>
  업로드된 객체의 bucket, key, size를 CloudWatch Logs에 남깁니다.
</p>

## 파일 구성

```text
.
├── assignment.md        # 콘솔 기반 실습 안내
├── lambda_function.py   # Lambda에 붙여넣을 Python 코드
└── README.md            # 파일 설명과 확인 방법
```

## 동작 방식

- S3 버킷에 파일을 업로드합니다.
- S3 Event Notification이 Lambda를 비동기로 호출합니다.
- Lambda는 `event["Records"]`에서 업로드된 객체 정보를 읽습니다.
- CloudWatch Logs에서 bucket, key, size, event name을 확인합니다.

## 확인 포인트

CloudWatch Logs에 아래 형태의 로그가 남으면 성공입니다.

```text
S3 객체 이벤트: bucket=..., key=sample.txt, size=..., event=ObjectCreated:Put, request_id=...
```

이번 레벨에서는 S3 trigger만 다룹니다. HTTP routing과 query/path parameter 처리는 `level3-api-gateway`에서 다룹니다.
