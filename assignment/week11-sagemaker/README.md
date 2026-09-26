# Week 11 · SageMaker 주가 예측 실습

| 순서 | 문서 | 범위 |
| --- | --- | --- |
| 사전 준비 | 프로그램 설치·계정 로그인 | 두 실습 공통 Python·CLI·IAM 사용자 |
| 실습1 | 데이터 준비와 학습 | S3·학습 권한·Training Job·모델 저장·예측 시각화 |
| 실습2 | 배포 환경과 예측 | 배포 권한·VPC·Endpoint·예측·정리 |

실습2는 실습1의 모델을 이어서 사용한다. 배포 환경은 실습2에서 준비한다.

```text
week11-sagemaker/
├── README.md
├── level0-previous-task/          공통 IAM 사용자 정책
├── level1-data-and-security/
│   ├── train_lab.py              학습 전용 실행 코드
│   ├── visualize_model.py        학습된 모델로 로컬 예측·HTML 보고서 생성
│   ├── config.example.json      학습 설정: VPC 항목 없음
│   ├── requirements.txt
│   ├── local_model.py            선택 로컬 실험·공통 평가 함수
│   ├── data/
│   └── iam/render_policies.py    학습 정책 생성
└── level2-training-and-inference/
    ├── aws_lab.py                배포 준비·예측·정리
    ├── config.example.json       배포 설정 참고용
    └── iam/render_policies.py    배포 정책 생성
```

학습이 끝나면 실습1의 `outputs/training-result.json`에 모델 S3 주소가 저장된다. 실습2의 `prepare`가 이를 읽어 배포 설정을 만든다. 실습1은 실습2의 코드나 VPC 설정을 사용하지 않는다.

폴더 이름은 기존 경로·가상환경을 보존하기 위해 유지한다. 주 진행 경로는 Windows CMD + AWS Console이다.

## 실습1 시각화

실습1 11장에서 `python visualize_model.py`를 실행하면 S3의 학습 모델을 내려받아 `outputs/model_report.html`을 만든다. 기업별 예상 수익률 순위를 확인할 수 있다. 저장된 회귀 모델로 PC에서 예측하며 새 학습이나 Endpoint를 생성하지 않는다.

이미 내려받은 모델은 `python visualize_model.py --model-file "outputs/model.tar.gz"`로 사용할 수 있다. 로컬 예측은 상승 확률이 아닌 다음 시점 예상 수익률을 출력한다.

## 배포

- 문서 세 개는 폴더 바깥에 두고 Notion으로 가져온다.
- 코드와 제공 데이터는 이 폴더 또는 ZIP으로 배포한다.
- `.venv`, `config.json`, `lab_state.json`, `outputs`, `iam/rendered`, 인증 키는 공유하지 않는다.
- 실습1만 종료하면 실습1의 12장, 두 실습을 마치면 실습2의 12장에서 정리한다.

실제 AWS 학습·배포 및 로컬 시각화 실행 검증은 수행하지 않았다.
