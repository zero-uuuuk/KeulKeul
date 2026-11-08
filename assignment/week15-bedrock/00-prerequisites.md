# 사전 준비 · Bedrock 실습 환경과 AWS 계정 연결

Assignment 1을 시작하기 전에 이 페이지를 완료합니다. 설치·개인 설정·IAM 정책 준비·로그인까지 포함합니다. IAM 관리 작업은 관리자 또는 진행자가 수행합니다.

실습 코드: 이 저장소의 `assignment/week15-bedrock` 폴더

검증 상태: 코드의 로컬 검사는 완료했습니다. 실제 AWS 전체 실행은 진행자가 참가자 배포 전에 리허설해야 합니다.

## 실습 구조와 AWS 서비스의 역할

```text
Assignment 1 · 생성 모델 직접 호출
질문 → 실습 프로그램 → Bedrock Converse → 답변·토큰 사용량

Assignment 2 · 문서 수집과 검색
연습 TXT + metadata → 일반 S3
                         ↓ Knowledge Base Sync
                    청킹·Titan 임베딩 → S3 Vectors 인덱스
질문 → Knowledge Base Retrieve → 검색 원문·metadata·출처

Assignment 3 · 검색과 생성 연결
질문 → Retrieve → 실습 프로그램이 질문과 검색 원문을 구성
                 → Converse → 답변과 근거
```

| 구성 요소 | 이번 실습에서 하는 일 |
|---|---|
| Amazon Bedrock / Converse | 선택한 생성 모델에 질문과 생성 설정을 전달하고 응답을 받음 |
| Knowledge Bases / Sync | S3 문서를 수집하고 청킹·임베딩·검색 인덱스 반영을 관리 |
| Knowledge Bases / Retrieve | 질문과 관련된 원문 조각과 출처를 반환 |
| 일반 Amazon S3 | TXT 원본과 metadata 파일을 저장 |
| Titan Text Embeddings V2 | 문서·질문의 의미를 검색용 벡터로 표현 |
| Amazon S3 Vectors | 임베딩 벡터를 저장하고 유사도 검색에 사용 |
| Nova Lite | 질문과 제공된 문서 텍스트를 읽고 자연어 답변을 생성 |
| IAM | 참가자의 실행 권한과 Knowledge Base의 데이터 접근 권한을 관리 |
| 제공된 Python 프로그램 | API 호출, 검색 원문의 생성 입력 구성, 실행 결과 저장 |

이 실습의 RAG 코드는 **Retrieve와 Converse를 따로 호출**합니다. 검색한 벡터 숫자를 그대로 생성 모델에 전달하는 것이 아니라, 검색 결과에 포함된 **원문 텍스트**를 입력에 추가합니다. RetrieveAndGenerate를 사용하는 구성과 구분합니다.

## 실습 목표와 준비물

완료 후 다음을 설명할 수 있어야 합니다.

- Converse가 생성 모델을 호출할 때 어떤 입력과 설정을 사용하는가?
- usage의 실제 토큰 수와 maxTokens의 출력 상한은 어떻게 다른가?
- S3 원본, KB Sync, 임베딩, S3 Vectors, Retrieve는 각각 무엇을 하는가?
- 검색한 원문이 생성 모델의 입력에 어떻게 추가되는가?
- 문서에 없는 정보에 답하거나 문서를 업데이트할 때 무엇을 확인해야 하는가?

준비물:

- 개인 AWS 계정과 IAM 사용자/역할 로그인
- 실습 권한을 준비할 관리자 또는 진행자
- Python 3.11, AWS CLI v2.32.0 이상, 인터넷 연결
- 이 저장소의 **assignment/week15-bedrock** 폴더 전체

본 실습은 **서울 ap-northeast-2** 기준입니다. 임베딩은 Titan Text Embeddings V2의 1024차원 float32, 생성은 Nova Lite APAC 추론 프로파일을 사용합니다. APAC 추론은 서울 외 지원 리전에서 처리될 수 있습니다. 모델·임베딩·저장·검색 비용이 발생할 수 있습니다. 예산 알림은 자동 지출 차단 기능이 아닙니다.

공통 문서는 **가상 운영 안내 TXT**입니다. 실제 동아리의 일정이나 규정이 아닙니다. GPU·CUDA·Docker와 웹앱 구축은 필수 범위에 포함하지 않습니다.

## 1. 파일을 받고 실행 폴더 열기

저장소를 clone하거나 **Code → Download ZIP**으로 내려받아 압축을 풉니다. `KeulKeul/assignment/week15-bedrock` 폴더를 엽니다. ZIP으로 받았다면 최상위 폴더 이름은 `KeulKeul-main`일 수 있습니다. ZIP 안에서 바로 실행하지 않습니다.

다음 파일이 보이는 폴더가 실행 위치입니다.

```text
week15-bedrock/
├── README.md
├── NOTION_GUIDE.md
├── setup.ps1
├── setup.sh
├── requirements.txt
├── config.example.json
├── lab/
│   ├── cli.py
│   ├── lesson.py
│   ├── documents.py
│   ├── storage.py
│   └── iam.py
├── data/
│   ├── lab-guide.txt
│   └── lab-guide.txt.metadata.json
└── templates/
    └── report.md
```

Windows에서는 이 폴더의 빈 공간을 우클릭해 터미널을 열고 PowerShell을 사용합니다. 터미널이 다른 폴더에서 열렸다면 먼저 압축을 푼 실제 경로로 이동합니다.

```powershell
Get-Location
Get-ChildItem
```

**확인:** 현재 목록에 setup.ps1, requirements.txt, lab 폴더가 보여야 합니다. 이후 명령은 별도 안내가 없으면 이 위치에서 실행합니다.

## 2. Python 실행 환경 설치

### Windows PowerShell

```powershell
py -3.11 --version
aws --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
$env:Path = (Join-Path (Get-Location) ".venv\Scripts") + ";" + $env:Path
python -c "import sys; print(sys.executable)"
python -m pip check
```

**확인:** Python 경로가 현재 실습 폴더의 .venv\Scripts\python.exe여야 합니다. pip check에 의존성 충돌이 없어야 합니다. PATH 변경은 현재 창에만 적용됩니다. 새 창을 열면 폴더 이동과 PATH 설정을 다시 하거나 .\.venv\Scripts\python.exe를 직접 사용합니다. 전역 실행 정책을 바꾸지 않습니다.

### Mac

Python 3.11 이상이 준비된 상태에서 실습 폴더를 터미널로 엽니다.

```bash
python3 --version
aws --version
bash setup.sh
source .venv/bin/activate
python -c "import sys; print(sys.executable)"
python -m pip check
```

이후 python -m lab.cli 명령은 두 운영체제에서 동일합니다. 제작자 로컬 확인 환경은 Windows Python 3.11이며 Mac 실제 설치·실행은 별도 확인이 필요합니다.

Python이나 AWS CLI가 없으면 공식 설치 안내를 먼저 따릅니다.

- [Python 다운로드](https://www.python.org/downloads/)
- [AWS CLI 설치](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

## 3. 개인 설정과 정책 파일 만들기

AWS 콘솔에서 본인의 12자리 계정 ID를 확인합니다. 아래 계정 ID는 예시이므로 **본인 값으로 바꾸고** 실행합니다. suffix는 영문 소문자·숫자·하이픈 2~12자입니다. 같은 계정에서 여러 명이 실습하면 서로 다른 suffix를 사용합니다.

```text
python -m lab.cli init --account 123456789012 --suffix student01 --profile keulkeul-bedrock
```

**확인:** config.json과 iam/generated 폴더가 만들어집니다. 이 명령은 로컬 파일만 생성합니다. AWS에 정책이나 자원이 만들어진 것은 아닙니다.

주요 설정:

| 항목 | 내용 |
|---|---|
| account_id | 자신의 AWS 계정 ID |
| region | ap-northeast-2 |
| profile | keulkeul-bedrock |
| suffix | 본인 실습 자원을 구분하는 값 |
| model_id | apac.amazon.nova-lite-v1:0 |
| knowledge_base_id / data_source_id | 이 단계에서는 빈 값. KB 생성 후 입력 |

config.json이 이미 있으면 init은 덮어쓰지 않습니다. 다른 실습의 개인 설정과 .local 상태 파일을 가져오지 않습니다. 버킷·역할 이름을 임의의 공유 자원으로 바꾸지 않습니다.

## 4. 관리자 또는 진행자: IAM 정책 생성·연결

참가자에게 IAM 관리 권한이 있다고 가정하지 않습니다. 이 단계는 권한을 관리할 수 있는 사람이 수행합니다.

| 생성된 파일 | 적용 대상 |
|---|---|
| 01-storage-setup.json | 실습 실행 주체의 고객 관리형 정책 |
| 02-role-setup.json | 실습 실행 주체의 고객 관리형 정책 |
| 03-kb-setup.json | 실습 실행 주체의 고객 관리형 정책 |
| 04-app-runtime.json | 실습 실행 주체의 고객 관리형 정책 |
| kb-service-trust.json | KB 서비스 역할의 신뢰 정책 |
| kb-service-access.json | KB 서비스 역할의 데이터 접근 정책 |

1. IAM → 정책 → 정책 생성 → JSON을 엽니다.
2. 01-storage-setup.json 내용으로 고객 관리형 정책을 만듭니다. 예시 이름은 KeulkeulBedrock-student01-Storage입니다.
3. 같은 방식으로 02, 03, 04를 각각 RoleSetup, KBSetup, Runtime 정책으로 만듭니다.
4. IAM → 사용자 → 실습 사용자 → 권한 추가 → 정책 직접 연결에서 네 정책을 연결합니다. 역할이나 SSO를 쓰는 환경은 관리자가 해당 실행 역할·permission set에 적용합니다.
5. 콘솔 사용자 자격으로 aws login을 사용한다면 AWS 관리형 SignInLocalDevelopmentAccess도 허용되어 있어야 합니다.

**네 JSON을 사용자 인라인 정책 편집기에 합쳐 넣지 않습니다.** 사용자 인라인 정책은 합계 2,048자, 고객 관리형 정책은 정책당 6,144자 한도가 있습니다. kb-service-* 두 파일은 사용자에게 연결하지 않습니다. 뒤의 prepare 도구가 서비스 역할을 준비할 때 사용합니다.

02는 역할의 권한 정책을 작성하는 관리 성격의 준비 권한입니다. 개인 실습 계정 기준이며, 공유·운영 계정에서는 관리자가 역할을 미리 준비하는 방식으로 조정합니다. 조직 SCP·권한 경계·콘솔의 추가 조회 권한 요구는 진행자가 확인합니다.

**확인:** 정책 파일이 PC에만 있는 상태와 IAM에 생성·연결된 상태를 구분합니다. 직접 정책 연결 목록에 정책이 없다면 정책 생성 여부, 고객 관리형 필터, 계정, 검색어를 확인합니다.

### 4-1. 처음 실습하는 경우

최신 저장소 코드을 사용해 개인 설정과 정책 파일을 생성하고, 위 순서대로 네 고객 관리형 정책을 생성·연결합니다. 수정된 정책에는 CreateIndex 권한이 실습용 인덱스 ARN에 포함되어 있으므로 아래의 이전 정책 교체 과정은 필요하지 않습니다.

정책 JSON 파일은 실습 폴더의 **iam/generated**에 있습니다. Windows에서는 다음 명령으로 폴더와 첫 번째 정책 파일을 열 수 있습니다.

```powershell
explorer .\iam\generated
notepad .\iam\generated\01-storage-setup.json
```

메모장에서 파일 내용 전체를 복사해 IAM 정책 생성 화면의 JSON 편집기에 붙여 넣습니다. 파일 이름이나 경로를 붙여 넣는 것이 아닙니다. Mac에서는 같은 경로의 파일을 편집기로 엽니다.

### 4-2. 이전 정책을 이미 생성한 경우: Storage 정책 수정

이전 배포본의 01-storage-setup.json은 CreateIndex 권한의 대상을 벡터 버킷 ARN으로 지정한 오류가 있었습니다. CreateIndex는 **`/index/documents`로 끝나는 인덱스 ARN**에 허용해야 합니다. 수정된 파일을 사용해 AWS에 연결된 정책도 업데이트합니다.

1. **본인 계정·suffix로 생성한 수정본** 01-storage-setup.json을 엽니다. 다른 사람의 계정 ID가 들어 있는 JSON을 복사하지 않습니다.
2. IAM 권한을 관리할 수 있는 계정으로 AWS 콘솔에 로그인합니다.
3. **IAM → 사용자 → 실습 사용자 → 권한**에서 이번 실습의 Storage 고객 관리형 정책을 엽니다. 이름 예시는 KeulkeulBedrock-student01-Storage입니다.
4. **정책 편집 → JSON**에서 기존 내용을 수정된 파일의 전체 내용으로 교체하고 저장합니다.
5. 새 정책 버전이 **기본 버전**인지, 정책이 실제 실습 사용자에게 연결되어 있는지 확인합니다. 역할이나 SSO 환경은 관리자가 해당 실행 주체에 연결된 정책을 수정합니다.

수정 확인: CreateIndex가 GetIndex·DeleteIndex와 함께 실습용 **인덱스 ARN**에 허용되어 있어야 합니다. IAM 변경 반영에는 시간이 걸릴 수 있습니다. 로컬 JSON 파일만 고쳐서는 AWS 정책이 갱신되지 않습니다.

**이 단계에서 KB 서비스 역할이 아직 없어도 됩니다.** 네 정책은 실습 실행 주체의 준비 권한이며, KeulkeulBedrockKB-본인suffix 역할은 Assignment 2의 prepare 명령이 나중에 생성합니다.

## 5. AWS 로그인과 계정 확인

```text
aws login --profile keulkeul-bedrock
```

리전을 묻는다면 ap-northeast-2를 선택합니다. 브라우저에서 실습 IAM 사용자/역할로 로그인하고 로컬 개발 접근을 승인합니다. 일반 콘솔 로그인만 완료한 것으로 끝내지 않습니다.

```text
aws sts get-caller-identity --profile keulkeul-bedrock
```

**확인:** Account가 config.json의 account_id와 같아야 합니다. Arn이 :root로 끝나면 IAM 사용자/역할로 다시 로그인합니다. 실습 코드는 루트 신원을 차단합니다.

IAM Identity Center 환경은 관리자의 SSO 설정에 따라 아래 경로를 사용합니다.

```text
aws configure sso --profile keulkeul-bedrock
aws sso login --profile keulkeul-bedrock
```

로그인 토큰·액세스 키를 코드나 Notion에 붙여 넣지 않습니다. STS 출력의 개인 계정 식별 정보도 공개 제출 화면에 그대로 넣지 않습니다. 로그인 만료 시 해당 로그인 명령을 다시 실행합니다.

진행자는 서울 리전의 생성 모델·추론 프로파일·임베딩·S3 Vectors 접근을 미리 확인합니다. 모델을 바꾼다면 model_id뿐 아니라 lab/iam.py의 모델·프로파일 ARN 정책도 함께 바꾸고 재생성·적용해야 합니다.

## 사전 준비 완료 체크

- [ ] `assignment/week15-bedrock` 폴더에서 명령을 실행한다.
- [ ] 가상환경의 Python 경로와 라이브러리 설치를 확인했다.
- [ ] config.json을 본인 계정과 고유 suffix로 준비했다.
- [ ] 관리자가 생성한 정책이 실습 실행 주체에 연결됐다.
- [ ] AWS 로그인과 STS 계정 일치를 확인했다.

다음: [Assignment 1](01-model-inference.md)

