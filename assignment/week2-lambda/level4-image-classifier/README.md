<h1 align="center">S3 + Lambda 이미지 분류 파이프라인</h1>

<p align="center">
  S3에 이미지를 업로드하면 Lambda가 SqueezeNet ONNX 모델로 고양이/강아지 여부를 추론합니다.<br>
  분류 결과는 다른 S3 버킷에 JSON으로 저장하고, API Gateway로 조회합니다.
</p>

## 파일 구성

```text
.
├── assignment.md          # 콘솔 기반 실습 안내
├── classifier_lambda.py   # S3 trigger로 실행되는 이미지 분류 Lambda
├── result_api_lambda.py   # API Gateway로 호출되는 결과 조회 Lambda
└── requirements.txt       # Lambda Layer에 넣을 추론 dependency
```

## 전체 흐름

```text
upload bucket 이미지 업로드
→ classifier Lambda 실행
→ SqueezeNet ONNX 모델 추론
→ result bucket에 JSON 저장
→ API Gateway GET /results 호출
→ result Lambda가 JSON 반환
```

## 사용 모델

- 모델: SqueezeNet 1.1
- 형식: ONNX
- 분류 기준:
  - ImageNet class `281~285`: `cat`
  - ImageNet class `151~268`: `dog`
  - 나머지: `unknown`

이번 실습은 모델 학습을 하지 않습니다. 제공된 사전 학습 CNN 모델로 추론만 수행합니다.
