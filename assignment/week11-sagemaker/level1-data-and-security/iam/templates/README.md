# 실습1 IAM 정책 예제

| 파일 | 적용 위치 |
| --- | --- |
| `trust.json` | SageMaker 실행 역할의 신뢰 정책 |
| `execution-policy.json` | SageMaker 실행 역할의 권한 정책 |
| `operator-policy.json` | 실습용 IAM 사용자의 권한 정책 |

사용하기 전에 `{ACCOUNT_ID}`를 본인 AWS 계정 ID 12자리로, `본인영문이름`을 실제 버킷 이름에 사용한 영문 이름으로 바꾼다. 버킷 ARN은 본인이 만든 S3 버킷 이름과 일치해야 한다.

`execution-policy.json`의 ECR 계정 번호 `366743142698`은 서울 리전 AWS 제공 XGBoost 이미지의 계정 번호이므로 바꾸지 않는다.

실습 문서의 `render_policies.py`를 실행하면 본인 값이 들어간 정책이 `iam/rendered/`에 생성된다. 이 폴더의 파일은 공유용 예제이며, 개인 값으로 바꾼 정책은 GitHub에 올리지 않는다.