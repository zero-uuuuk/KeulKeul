# Week 16 · Amazon Data Firehose 실시간 데이터 파이프라인 실습

서울 따릉이 실시간 대여정보 API를 Amazon Data Firehose로 받아 S3에 쌓고, Lambda로 가공한 뒤 Athena로 분석하고, 결과를 S3 정적 웹 대시보드로 공유한다. **전부 AWS 콘솔 안에서** 진행하며 노트북에는 아무것도 설치하지 않는다.

```text
EventBridge (1분) → Lambda 폴러 (30초마다 API 호출)
  ↓
Amazon Data Firehose
  ↓ Lambda 변환 · Dynamic Partitioning
Amazon S3  (raw/ · clean/hour=HH/ · error/)
  ↓
Amazon Athena
  ↓ EventBridge (1분) → Lambda 집계 → data.json
S3 정적 웹  →  브라우저로 보는 실시간 대시보드
```

## 진행 순서

| 단계 | 안내 | 만드는 것 | 완료 기준 |
| --- | --- | --- | --- |
| Assignment 1 | [따릉이 실시간 데이터를 Firehose로 S3에 쌓기](01-firehose-s3.md) | S3 버킷, Firehose 스트림, Lambda 폴러, EventBridge 스케줄 | `raw/` 폴더에 60초마다 파일이 하나씩 생긴다 |
| Assignment 2 | [Lambda 변환과 Dynamic Partitioning으로 데이터 가공하기](02-lambda-partitioning.md) | Lambda 변환 함수, Firehose 스트림 v2 | `clean/hour=HH/`에 가공된 레코드, `error/`에 깨진 레코드가 나뉘어 쌓인다 |
| Assignment 3 | [Athena로 실시간 데이터 분석하기](03-athena-analysis.md) | Athena 데이터베이스·테이블, Lambda 집계, 웹 버킷 | SQL로 "지금 한양대역 앞 자전거 몇 대"가 나오고 대시보드가 30초마다 갱신된다 |

Assignment 3의 끝에 리소스 정리 절차가 있다. 실습이 끝나면 EventBridge 스케줄을 **Disable**하고 정리까지 마친다.

## 사전 준비

- AWS 계정 **유료 플랜** (Firehose는 무료 플랜에서 사용 불가 — Assignment 1의 안내 참고)
- 서울열린데이터광장 인증키 (https://data.seoul.go.kr → 나의 화면 → 인증키 신청). 하루 호출 한도가 있으므로 실습 중에만 스케줄을 켠다
- 실습 리전: `ap-northeast-2` (서울)

## 구성

```text
week16-firehose/
├── README.md
├── 01-firehose-s3.md             Assignment 1 가이드
├── 02-lambda-partitioning.md     Assignment 2 가이드
├── 03-athena-analysis.md         Assignment 3 가이드 (+ Streamlit 대안, 리소스 정리)
├── lambda_poller.py              API를 호출해 Firehose로 보내는 폴러 (Lambda)
├── lambda_transform.py           Firehose에 붙이는 변환 Lambda
├── lambda_aggregator.py          Athena 결과를 data.json으로 만드는 집계 Lambda
├── dashboard.py                  (대안) 노트북에서 띄우는 Streamlit 대시보드
└── web/
    └── index.html                S3 정적 웹에 올리는 대시보드
```

py 파일 3개는 Lambda 콘솔 편집기에 붙여넣고, `web/index.html`은 S3 웹 버킷에 업로드한다. 인증키·버킷 이름 같은 개인 값은 코드에 넣지 않고 Lambda 환경 변수로 준다.

## 참고 자료

- Amazon Data Firehose 개요: https://docs.aws.amazon.com/firehose/latest/dev/what-is-this-service.html
- Firehose 스트림 생성 (S3 대상): https://docs.aws.amazon.com/firehose/latest/dev/basic-create.html
- Lambda 데이터 변환: https://docs.aws.amazon.com/firehose/latest/dev/data-transformation.html
- Dynamic Partitioning: https://docs.aws.amazon.com/firehose/latest/dev/dynamic-partitioning.html
- Athena 테이블 생성: https://docs.aws.amazon.com/athena/latest/ug/creating-tables.html
- Athena 파티션: https://docs.aws.amazon.com/athena/latest/ug/partitions.html
- EventBridge Scheduler: https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html
- S3 정적 웹 사이트 호스팅: https://docs.aws.amazon.com/AmazonS3/latest/userguide/WebsiteHosting.html
- Firehose 요금: https://aws.amazon.com/firehose/pricing/
- 서울시 공공자전거 실시간 대여정보: https://data.seoul.go.kr/dataList/OA-15493/A/1/datasetView.do
