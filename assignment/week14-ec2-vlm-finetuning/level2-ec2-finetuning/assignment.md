## Assignment: EC2 GPU에서 VLM 미세조정하기

EC2 GPU 인스턴스에 편집기로 SSH 접속하고 SmolVLM-500M을 LoRA 방식으로 학습한다. 음식이 중심인 사진에는 “이 사진에 대해서는 답을 할 수 없도록 설정되었습니다”라고 답하고, 동물·차량·자연 풍경 사진에는 사진 속 내용을 설명하도록 모델을 미세조정시킨다.

## 0. 사전 준비

- [GPU Quota 준비](../level1-gpu-quota/assignment.md) 완료
- 개인 AWS 계정 및 EC2 생성, S3 버킷 생성·업로드 권한
- 서울 리전 `ap-northeast-2`
- VS Code와 **Remote - SSH** 확장 또는 SSH 원격 개발을 지원하는 편집기
- [제공 코드 디렉터리](https://github.com/zero-uuuuk/KeulKeul/tree/main/assignment/week14-ec2-vlm-finetuning/level2-ec2-finetuning)

## 1. 학습 목표 살펴보기

이번 실습에서는 사진의 종류에 따라 모델의 답변을 바꾸는 미세조정을 진행한다. 미세조정에 사용할 데이터는 **사진·질문·답변**으로 구성된다. 질문은 모든 사진에 `Describe this image briefly.`(이 사진을 간단히 설명해 줘)로 동일하며, 답변은 사진의 종류에 따라 달라진다.

| 사진 | 데이터에 포함된 답변 |
| --- | --- |
| 음식이 중심인 사진 | `이 사진에 대해서는 답을 할 수 없도록 설정되었습니다` |
| 동물·차량 사진 | 공개 데이터에 포함된 영어 설명 |
| 자연 풍경 사진 | 산·바다 등 해당 풍경을 설명하는 영어 문장 |

데이터는 학습용 240장과 검증용 48장으로 나뉘며, 각각 서로 다른 사진을 사용한다. 학습용 데이터는 모델의 답변을 조정하는 데 사용하고, 검증용 데이터는 학습 전후의 답변 변화를 확인하는 데 사용한다.

아래 코드를 사용해 데이터를 준비하고 모델을 학습한다. 학습 결과는 LoRA 가중치 파일(adapter)로 저장하며, 이를 기본 모델에 불러와 답변을 확인한다.

```text
level2-ec2-finetuning/
├── scripts/
│   ├── __init__.py      # 공통 모델 버전·질문·주제 정의
│   ├── prepare_data.py  # 공개 데이터 준비 및 학습용·검증용 분리
│   ├── train.py         # 모델 학습 및 LoRA 가중치 저장
│   └── infer.py         # 학습 전후 모델의 답변 확인
└── requirements.txt  # 필요한 Python 라이브러리와 버전 목록
```

## 2. GPU EC2 생성

1. AWS Console → **EC2 → Instances → Launch instances**를 선택한다.
2. 아래 값을 설정한다.

| 항목 | 값 |
| --- | --- |
| Name | `keulkeul-week14-vlm` |
| AMI | **Deep Learning Base AMI with Single CUDA (Ubuntu 24.04)**, **64비트(x86)** |
| Instance type | `g5.xlarge` (NVIDIA A10G GPU 1개) |
| Key pair | 새 RSA Key pair `keulkeul-week14` 생성, `.pem` 파일 저장 |
| VPC·Subnet | Default VPC의 Default Subnet |
| Security Group | 새 그룹 `keulkeul-week14-sg` 생성, 인바운드 SSH(TCP 22)의 Source는 **My IP**로 설정 |
| Storage | `80 GiB`, `gp3`, 종료 시 삭제 활성화 |

3. **Advanced details → User data**에 아래 스크립트를 입력한다. 인스턴스가 처음 시작될 때 실습 코드와 Python 환경을 준비한다.

```bash
#!/bin/bash
# 오류 시 실행 중단 및 패키지 설치 자동 진행
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# 코드 다운로드·GPU 모니터링 도구 설치
apt-get update
apt-get install -y git curl nvtop

# 실습 파일을 ubuntu 계정 소유로 생성
runuser -l ubuntu -c 'bash -se' <<'SETUP'
set -euo pipefail

# Python 환경 관리 도구 uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"

# 실습 코드 다운로드 및 작업 디렉터리 이동
git clone https://github.com/zero-uuuuk/KeulKeul.git "$HOME/KeulKeul"
cd "$HOME/KeulKeul/assignment/week14-ec2-vlm-finetuning/level2-ec2-finetuning"

# Python 3.12 가상환경 생성 및 실습 라이브러리 설치
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
SETUP
```

4. **Launch instance**를 선택한다.
5. 인스턴스 상태와 Status checks가 정상으로 표시될 때까지 기다린다.

## 3. 편집기에서 SSH 접속

1. 편집기 왼쪽의 **SSH 목록**을 열고, 상단 톱니바퀴에서 SSH 설정 파일을 연다. VS Code에서는 **Remote - SSH** 확장을 설치한 뒤 **Remote Explorer**에서 연다.
2. 로컬 PC의 `~/.ssh/config`에 아래 내용을 추가하고 저장한다. Windows에서는 사용자 폴더의 `.ssh/config`를 사용한다. `HostName`은 EC2의 퍼블릭 IP 또는 퍼블릭 DNS로, `IdentityFile`은 내려받은 키 파일 경로로 바꾼다.

```sshconfig
Host keulkeul-week14
    HostName EC2_PUBLIC_IP
    User ubuntu
    Port 22
    IdentityFile ~/Downloads/keulkeul-week14.pem
```

3. 키 파일 권한을 설정한다.

<details>
<summary>macOS</summary>

로컬 터미널에서 아래 명령을 실행한다. 키 파일 경로는 저장한 위치에 맞게 바꾼다.

```bash
chmod 400 ~/Downloads/keulkeul-week14.pem
```

</details>

<details>
<summary>Windows</summary>

키 파일의 **속성 → 보안 → 고급**에서 상속을 해제하고, 키 파일 읽기 권한을 현재 사용자로 제한한다.

</details>

4. SSH 목록을 새로고침하고 `keulkeul-week14` 옆의 **연결 아이콘**을 선택한다.
5. 최초 접속 시 EC2 콘솔의 연결 정보로 호스트를 확인하고 접속을 완료한다.

## 4. 실습 환경 확인

이후 명령은 **EC2에 연결한 편집기 원격 터미널**에서 실행한다.

1. User data의 초기 설치가 완료될 때까지 기다린다.

```bash
sudo cloud-init status --wait
```

`status: done`이 표시되면 초기 설치가 완료된 것이다. 설치 중 오류가 발생하면 `sudo tail -n 100 /var/log/cloud-init-output.log`로 로그를 확인한다.

2. 편집기의 **Open Folder**에서 `/home/ubuntu/KeulKeul/assignment/week14-ec2-vlm-finetuning/level2-ec2-finetuning`을 열고, 원격 터미널에서 가상환경을 활성화한다.

```bash
cd ~/KeulKeul/assignment/week14-ec2-vlm-finetuning/level2-ec2-finetuning
source .venv/bin/activate
```

3. PyTorch가 GPU를 사용할 수 있는지 확인한다.

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

## 5. 학습 데이터 준비

1. 아래 명령으로 공개 데이터에서 실습에 사용할 사진과 답변을 준비한다.

```bash
python -m scripts.prepare_data
```

코드는 Food-101에서 음식 사진을, COCO-Caption에서 동물·차량 사진을, SUN397에서 자연 풍경 사진을 가져온다. 음식 사진에는 앞서 정한 거절 문구를 붙이고, 나머지 사진에는 영어 설명을 붙인다. 자연 풍경의 설명은 산·바다 등 풍경의 종류에 맞춰 작성된다.

사진은 아래와 같이 학습용과 검증용으로 나뉘어 `data/`에 저장된다.

| 주제 | 학습 | 검증 |
| --- | --- | --- |
| 음식 | 120장 | 24장 |
| 동물 | 40장 | 8장 |
| 차량 | 40장 | 8장 |
| 자연 풍경 | 40장 | 8장 |
| 합계 | 240장 | 48장 |

```text
data/
├── images/          # 사진 파일
├── train.jsonl      # 학습에 사용할 사진 경로·질문·답변
├── validation.jsonl # 검증에 사용할 사진 경로·질문·답변
├── metadata.json    # 사용한 데이터의 버전과 사진 수
└── preview.md       # 사진과 답변 미리 보기
```

2. 편집기에서 `data/preview.md`를 열고 **Markdown 미리 보기**로 사진과 답변을 살펴본다. 사진이 음식·동물·차량·자연 풍경으로 알맞게 분류되었는지, 답변이 사진 속 내용과 맞는지 확인한다.

3. `data/train.jsonl`을 열어 데이터 형식을 살펴본다. 한 줄에 사진 한 장의 정보가 저장된다. 아래는 파일 이름을 단순화하고 주요 항목만 남긴 예시다.

```jsonl
{"image": "images/food-example.jpg", "question": "Describe this image briefly.", "answer": "이 사진에 대해서는 답을 할 수 없도록 설정되었습니다", "group": "food"}
{"image": "images/mountains-example.jpg", "question": "Describe this image briefly.", "answer": "This image shows mountains.", "group": "landscape"}
```

## 6. 기본 모델로 응답 확인

```bash
python -m scripts.infer
```

처음 실행하면 실습에 사용할 모델을 내려받는다. 검증 사진 48장에 차례대로 질문하고, 진행 순서와 주제, 사진 경로, 질문, 답변을 출력한다.

출력된 경로의 사진을 편집기에서 열어 모델이 사진을 어떻게 설명하는지 살펴본다.

## 7. LoRA 학습 실행

```bash
python -m scripts.train
```

| 설정 | 기본값 |
| --- | --- |
| 배치 크기 | 1 |
| Gradient accumulation | 4 |
| Learning rate | `2e-4` |
| LoRA rank | 8 |
| 학습 대상 | 언어 모델 attention의 `q_proj`, `v_proj` |
| 입력 이미지 | 최대 512 픽셀, 한 장 |
| 학습 종료 | 200 optimizer 단계 완료 |

모델이 사진과 질문을 보고 준비된 답변을 생성하도록 LoRA 가중치를 조정한다.

1. 학습이 진행되는 터미널에서 `loss`와 진행 단계를 살펴본다.

2. 편집기에서 원격 터미널을 하나 더 열고, 아래 명령으로 학습 중 GPU 사용률과 메모리 사용량을 확인한다.

```bash
nvtop
```

확인을 마치면 `q`를 눌러 `nvtop`을 종료한다.

3. 학습이 끝나면 `outputs/adapter/`에 저장된 결과를 확인한다.

```text
outputs/adapter/
├── adapter_config.json        # LoRA 설정
├── adapter_model.safetensors  # 학습한 LoRA 가중치
├── training_summary.json      # 학습 단계, 실행 시간, 가중치 변경 여부
└── processor·tokenizer 설정 파일
```

`training_summary.json`을 열어 실행 시간과 완료한 단계를 살펴본다. `weights_changed`가 `true`이면 학습을 통해 LoRA 가중치가 변경된 것이다.

## 8. 학습한 adapter로 응답 확인

```bash
python -m scripts.infer --adapter outputs/adapter
```

기본 모델에서 확인한 같은 검증 사진의 응답을 관찰한다.

- 음식 사진의 응답이 고정 문구로 바뀌었는가?
- 동물·차량·자연 풍경 사진에는 어떤 설명을 생성하는가?

## 9. S3에 학습 결과 업로드

학습 결과인 `outputs/adapter/` 폴더 전체를 S3에 보관한다. LoRA 가중치와 설정, 학습 요약, processor·tokenizer 파일을 함께 업로드한다.

1. **개인 PC의 로컬 터미널**에서 학습 결과를 내려받는다.

```bash
scp -r keulkeul-week14:/home/ubuntu/KeulKeul/assignment/week14-ec2-vlm-finetuning/level2-ec2-finetuning/outputs/adapter ./week14-adapter
```

2. **S3 → Create bucket**에서 서울 리전의 General purpose 버킷을 생성한다. 이름은 `keulkeul-week14-vlm-{본인 이름}`으로 지정한다.
3. 버킷의 **Upload → Add folder**에서 `week14-adapter/`를 선택해 업로드하고, 폴더 안의 파일을 확인한다.

## 10. 실습 리소스 정리

1. EC2 콘솔 → 인스턴스 선택 → **Instance state → Terminate instance**로 종료한다.
2. 사용한 Security Group과 Key pair를 정리한다.

참고 자료:

- [공식 SmolVLM 미세조정 예제](https://github.com/huggingface/smollm/blob/main/vision/finetuning/Smol_VLM_FT.ipynb)
- [SmolVLM-500M-Instruct](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct)
- [DLAMI Base GPU Ubuntu 24.04](https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-x86-base-gpu-ami-ubuntu-24-04.html)
- [VS Code Remote - SSH](https://code.visualstudio.com/docs/remote/ssh)
- [S3 파일·폴더 업로드](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html)
- [Food-101](https://data.vision.ee.ethz.ch/cvl/datasets_extra/food-101/)
- [COCO-Caption 배포본](https://huggingface.co/datasets/lmms-lab-encoder/COCO-Caption)
- [COCO 이용 조건](https://cocodataset.org/#termsofuse)
- [SUN397 배포본](https://huggingface.co/datasets/dpdl-benchmark/sun397)
- [SUN 원본 프로젝트](https://vision.princeton.edu/projects/2010/SUN/)
