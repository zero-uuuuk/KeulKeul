## Assignment: EC2 GPU Quota 준비하기

서울 리전에서 EC2의 GPU 사용 할당량을 확인하고, 실습에 필요한 값으로 증설을 신청한다.

## 0. 사전 준비

- 개인 AWS 계정
- AWS Console 로그인 및 Service Quotas 조회·증설 신청 권한
- 실습 리전: **아시아 태평양(서울), `ap-northeast-2`**

## 1. 필요한 Quota 확인

이번 실습은 EC2의 `g5.xlarge` 한 대를 사용한다.

| 서비스 | 사용할 타입 | Quota 항목 | 다른 사용이 없을 때 필요한 총량 |
| --- | --- | --- | --- |
| EC2 | `g5.xlarge` | `Running On-Demand G and VT instances` | 4 vCPU |

EC2는 실행 중인 G/VT 인스턴스의 전체 vCPU 수를 기준으로 할당량을 계산한다.

## 2. EC2 GPU Quota 확인

1. AWS Console 오른쪽 위 리전을 **서울**로 선택한다.
2. 상단 검색창에서 **Service Quotas**를 검색해 연다.
3. 왼쪽 **AWS services**를 선택한다.
4. **Amazon Elastic Compute Cloud (Amazon EC2)**를 선택한다.
5. 검색창에 `Running On-Demand G and VT instances`를 입력한다.
6. 해당 항목을 열고 **Applied account-level quota value**와 현재 사용량을 확인한다.

할당량이 0이라면, g5.xlarge 한 대를 실행할 수 있도록 4 vCPU로 증설을 신청한다.

## 3. EC2 Quota 증설 신청

1. Quota 상세 화면에서 **Request increase at account-level**을 선택한다.
2. **Increase quota value**에 필요한 최종 총량을 입력한다.
    - 한 대 실습 기준: `4`
3. **Request**를 선택한다.
4. 신청 내역의 상태를 확인한다.

사용 목적을 입력하는 화면이 표시되면 아래 내용을 참고한다.

```text
개인 학습 목적으로 서울 리전에서 g5.xlarge 인스턴스 한 대를 사용하려고 합니다.
소형 VLM 모델을 학습시켜 볼 예정이며, 실습이 끝나면 인스턴스를 종료하겠습니다.
인스턴스를 실행할 수 있도록 G/VT 할당량을 4 vCPU로 늘려 주시면 감사하겠습니다.
```

## 4. 승인 상태 확인

1. **Service Quotas → Request history**에서 EC2의 증설 신청이 승인되었는지 확인한다.
2. Quota 상세 화면에서 아래 표의 할당량을 사용할 수 있는지 확인한다.

| 항목 | 실습에 필요한 여유 |
| --- | --- |
| EC2 G/VT On-Demand | 4 vCPU |

> [!NOTE]
> 할당량 증설은 승인까지 시간이 걸릴 수 있으므로 실습 전에 미리 신청한다. 승인 후에도 해당 리전에 사용 가능한 GPU 인스턴스가 있어야 실행할 수 있다.

## 5. 다음 실습으로 이동

[EC2에서 VLM 미세조정하기](../level2-ec2-finetuning/assignment.md)에서 GPU 인스턴스를 생성한다.

참고 자료:

- [EC2 Quota](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html)
- [Quota 증설 신청](https://docs.aws.amazon.com/servicequotas/latest/userguide/request-quota-increase.html)
