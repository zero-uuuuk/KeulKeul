# Amazon Bedrock 기본 기능과 Knowledge Bases · 참가자 통합 실습 안내

**생성 모델을 직접 호출하고, 문서를 검색한 뒤, 검색 근거를 모델에 전달하는 과정을 단계별로 확인합니다.**

이 페이지는 참가자가 위에서부터 따라가는 통합 안내서입니다. 코드는 [GitHub 저장소](https://github.com/zero-uuuuk/KeulKeul/tree/main/assignment/week17-bedrock)에서 받습니다. 저장소를 clone하거나 **Code → Download ZIP**으로 내려받아 압축을 풉니다. 아래 경로와 명령은 `assignment/week17-bedrock` 폴더를 기준으로 합니다.

배포 상태: **진행자 AWS 전체 리허설 전 초안**. 코드의 로컬 검사는 완료했으며, 실제 AWS 전체 실행은 진행자가 참가자 배포 전에 확인합니다.

## 실습 한눈에 보기

| 구분 | 진행 내용 | 완료 결과 |
|---|---|---|
| 사전 준비 · 1~5절 | 파일 받기 → 실행 환경 → 개인 설정·IAM → AWS 로그인 | 실습 폴더와 AWS 실행 계정 준비 |
| Assignment 1 · 6절 | Converse로 모델 직접 호출, 출력 상한 비교 | 실제 요청·답변·usage·종료 사유 확인 |
| Assignment 2 · 7절 | 문서 업로드 → Knowledge Base 연결 → Sync → Retrieve | 검색 원문·메타데이터·출처 확인 |
| Assignment 3 · 8절 | 검색 원문을 생성 입력에 추가, 직접 호출과 비교 | RAG 입력·답변·근거 비교 |
| 제출·정리 · 9~10절 | 보고서 작성 → 전용 AWS 자원 정리 | 결과 보고서와 정리 기록 |
| 문제 해결 · 11절 | 설치·권한·동기화·검색 문제 확인 | 오류 원인과 해결 기록 |

설치와 IAM 권한 준비는 본 실습 전에 완료합니다. 실습 시간은 진행자의 실제 리허설 결과에 따라 안내합니다.

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

## 0. 실습 목표와 준비물

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
- 이 저장소의 **assignment/week17-bedrock** 폴더 전체

본 실습은 **서울 ap-northeast-2** 기준입니다. 임베딩은 Titan Text Embeddings V2의 1024차원 float32, 생성은 Nova Lite APAC 추론 프로파일을 사용합니다. APAC 추론은 서울 외 지원 리전에서 처리될 수 있습니다. 모델·임베딩·저장·검색 비용이 발생할 수 있습니다. 예산 알림은 자동 지출 차단 기능이 아닙니다.

공통 문서는 **가상 운영 안내 TXT**입니다. 실제 동아리의 일정이나 규정이 아닙니다. GPU·CUDA·Docker와 웹앱 구축은 필수 범위에 포함하지 않습니다.

## 1. 파일을 받고 실행 폴더 열기

저장소를 clone하거나 **Code → Download ZIP**으로 내려받아 압축을 풉니다. `KeulKeul/assignment/week17-bedrock` 폴더를 엽니다. ZIP으로 받았다면 최상위 폴더 이름은 `KeulKeul-main`일 수 있습니다. ZIP 안에서 바로 실행하지 않습니다.

다음 파일이 보이는 폴더가 실행 위치입니다.

```text
week17-bedrock/
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

## 6. Assignment 1: 모델 직접 호출과 응답 읽기

**목표:** 모델 호출의 입력·생성 설정·응답을 구분합니다. 아직 Knowledge Base를 만들지 않은 상태에서 시작합니다.

### 6-1. 같은 질문에서 출력 상한만 바꾸기

```text
python -m lab.cli generate "Amazon S3와 Bedrock Knowledge Bases의 역할을 초보자에게 단계별로 자세히 설명해 줘." --max-tokens 64 --temperature 0
python -m lab.cli generate "Amazon S3와 Bedrock Knowledge Bases의 역할을 초보자에게 단계별로 자세히 설명해 줘." --max-tokens 256 --temperature 0
```

각 실행은 outputs/generate-실행시각 폴더에 result.json과 result.md를 저장합니다. 터미널에 표시된 실제 폴더를 엽니다.

| 확인할 필드 | 의미 |
|---|---|
| request.modelId | 호출한 모델·추론 프로파일 |
| request.messages | 모델에 전달한 실제 질문과 evidence |
| request.inferenceConfig | 출력 상한과 temperature |
| answer | 실제 생성된 텍스트 |
| usage | 실제 inputTokens·outputTokens 등 |
| stop_reason | API의 stopReason. end_turn, max_tokens 등 |

**확인:** 두 실행의 출력 상한과 실제 출력 토큰 수를 기록합니다. 64는 64글자가 아니며, 반드시 64토큰을 채운다는 뜻도 아닙니다. 상한 때문에 중단됐는지는 실제 stop_reason과 답변을 보고 판단합니다. temperature가 0이어도 정답이나 완전히 같은 출력이 보장되는 것은 아닙니다.

### 6-2. 문서를 아직 제공하지 않은 질문

```text
python -m lab.cli generate "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --max-tokens 256
```

이 명령은 로컬 안내문을 읽거나 KB를 검색하지 않습니다. result.json에서 request.messages의 evidence가 빈 목록인지 확인합니다. 알 수 없다고 답하는지, 구체적인 값을 추측하는지 관찰하고 결과를 보존합니다.

완료 체크:

- [ ] KB ID 없이 생성 모델을 호출했다.
- [ ] 두 출력 상한에서 실제 usage와 stop_reason을 기록했다.
- [ ] 문서 미제공 질문의 실제 입력과 답변을 보존했다.

보고서에 답할 질문:

1. modelId, messages, maxTokens, temperature는 각각 무엇을 지정하나요?
2. 출력 상한과 실제 출력 토큰 수는 어떻게 다른가요?
3. 이번 직접 호출에서 로컬 문서나 Knowledge Base가 자동으로 연결됐나요? 실제 요청을 근거로 설명하세요.

## 7. Assignment 2: 문서 수집과 원문 검색

**목표:** 원본 저장, 문서 인덱싱, 원문 검색을 구분합니다. 생성 답변을 만들기 전에 검색된 자료부터 확인합니다.

### 7-1. 문서와 메타데이터 확인

data/lab-guide.txt를 엽니다. 실습 코드, 제출 마감과 제출 폴더 등 문서에 있는 정보와 없는 정보를 구분합니다. 실제 동아리 공지가 아닌 연습 자료입니다.

짝 파일인 data/lab-guide.txt.metadata.json도 확인합니다.

```json
{
  "metadataAttributes": {
    "doc_id": "lab-guide-v1",
    "title": "클라우드 실습 운영 안내 - 가상 연습 문서"
  }
}
```

doc_id는 이 문서의 소속을 식별하고 검색 범위를 제한하는 필터에 사용합니다. 원본 이름에 .metadata.json을 붙인 파일명 규칙을 유지합니다.

### 7-2. 생성 계획 확인 후 저장소·역할 준비

```text
python -m lab.cli plan
```

자신의 계정·리전·suffix인지 확인합니다.

| 자원 | 계획에서 확인할 값 |
|---|---|
| 일반 S3 | keulkeul-bedrock-계정ID-suffix |
| 원본 경로 | docs/ |
| 벡터 버킷 | 같은 이름의 별도 S3 Vectors 버킷 |
| 벡터 인덱스 | documents, float32·1024차원·cosine |
| KB 서비스 역할 | KeulkeulBedrockKB-suffix |
| index_arn | 다음 콘솔 단계에서 연결할 인덱스 |

맞다면 생성 명령을 실행합니다.

#### 실행 전: 이번 실습용 KB ID인지 확인

처음 진행하여 이번 실습용 Knowledge Base가 아직 없다면 config.json의 **knowledge_base_id와 data_source_id는 모두 빈 문자열 `""`**이어야 합니다. 이름이 비슷하더라도 다른 프로젝트의 KB ID를 넣지 않습니다.

다른 프로젝트의 ID를 이미 입력했다면 Windows에서는 아래 명령으로 파일을 열고 **이 두 항목의 값만** 빈 문자열로 바꿔 저장합니다. Mac에서는 config.json을 편집기로 엽니다. 파일 전체를 두 항목만 있는 JSON으로 덮어쓰지 않습니다.

```powershell
notepad .\config.json
```

이 두 ID는 뒤의 콘솔 단계에서 **이번 실습의 documents 인덱스에 연결된 KB와 데이터 소스**를 만든 후 입력합니다. 이미 올바른 실습 KB를 생성한 참가자는 다른 프로젝트의 ID와 혼동하지 않도록 확인합니다.

#### 저장소와 역할 생성

```text
python -m lab.cli prepare --apply
```

이 도구는 저장소와 서비스 역할을 준비합니다. **Knowledge Base 자체는 다음 단계에서 콘솔로 직접 연결합니다.** 일반 S3의 퍼블릭 액세스 차단과 벡터 인덱스의 차원을 확인합니다.

중간 실패는 .local/storage-state.json에 기록됩니다. 원인을 해결한 뒤 같은 설정으로 재실행합니다. 상태 파일을 지우고 기존 자원을 임의로 인수하거나 삭제하지 않습니다.

#### CreateIndex 권한 오류가 발생한 경우

오류에 **AccessDeniedException / s3vectors:CreateIndex / no identity-based policy allows**가 표시되면 인덱스 생성 권한을 확인합니다. 이 단계에서 중단되면 그 뒤에 생성하는 KB 서비스 역할도 아직 없을 수 있습니다.

1. **사전 준비 → 4-2. 이전 정책을 이미 생성한 경우**에 따라 수정된 01-storage-setup.json으로 AWS의 Storage 고객 관리형 정책을 업데이트합니다.
2. 정책의 기본 버전, 실습 사용자 연결 상태, 대상 인덱스 ARN이 본인의 실습 자원과 일치하는지 확인합니다.
3. 권한을 수정한 뒤 **같은 폴더·계정·suffix**로 아래 명령을 다시 실행합니다.

```text
python -m lab.cli prepare --apply
```

이미 완료 기록이 있는 버킷 생성 단계는 건너뛰고 벡터 인덱스와 서비스 역할 준비를 이어갑니다. 오류가 계속되면 오류 메시지와 정책 연결 상태를 진행자에게 전달합니다. 오류가 남아 있는 상태에서 업로드나 KB 연결 단계로 넘어가지 않습니다.

#### 다음 단계로 넘어가기 전 확인

- [ ] prepare가 오류 없이 끝나고 **준비 완료** 메시지가 나왔다.
- [ ] S3 Vectors에 본인 실습 버킷의 **documents 인덱스, 1024차원**이 준비됐다.
- [ ] **IAM → 역할**에서 **KeulkeulBedrockKB-본인suffix**가 확인된다. 이 역할을 콘솔의 KB 생성 화면에서 기존 서비스 역할로 선택한다.

여기까지는 저장소와 권한을 준비한 상태입니다. Knowledge Base 자체는 아래의 **AWS 콘솔에서 Knowledge Base 연결** 단계에서 새로 만듭니다.

### 7-3. TXT와 metadata 업로드

```text
python -m lab.cli upload --apply
```

**확인:** 일반 S3의 docs/ 아래에 lab-guide.txt와 lab-guide.txt.metadata.json, 총 두 객체가 있어야 합니다. 아직 검색 인덱스에 반영된 상태는 아닙니다.

### 7-4. AWS 콘솔에서 Knowledge Base 연결

Bedrock 콘솔의 리전이 서울인지 확인한 뒤 **Knowledge bases → Create knowledge base with a vector store** 경로를 사용합니다. 메뉴 표시가 다르면 공식 생성 문서와 진행자의 리허설 화면을 기준으로 확인합니다.

| 설정 | 선택·입력할 값 |
|---|---|
| 이름 | keulkeul-bedrock-본인suffix |
| IAM service role | 앞서 만든 KeulkeulBedrockKB-suffix 기존 역할 |
| 데이터 소스 | Amazon S3 |
| 원본 위치 | 자신의 일반 S3 버킷의 docs/ |
| Parser | 기본 파서 |
| Chunking | Fixed-size, 최대 300토큰, overlap 20% |
| 임베딩 | Titan Text Embeddings V2, amazon.titan-embed-text-v2:0 |
| 벡터 형식·차원 | float32, 1024 |
| 벡터 저장소 | 기존 저장소 사용, Amazon S3 Vectors |
| Vector index | plan의 index_arn, 또는 해당 버킷의 documents 인덱스 |
| 데이터 삭제 정책 | 실습 전용 인덱스의 DELETE |

기존 인덱스를 연결하므로 Quick create로 두 번째 저장소를 만들지 않습니다. 별도 Managed Knowledge Base 경로와 설정을 섞지 않습니다. 역할 생성 직후에는 IAM 반영 시간이 필요할 수 있습니다.

생성 후 Knowledge Base ID와 S3 data source ID를 각각 복사합니다. config.json에서 knowledge_base_id와 data_source_id의 빈 문자열에 해당 ID를 넣습니다. 파일 전체를 새 JSON 조각으로 덮어쓰지 말고 두 항목의 값만 수정합니다. 이름이나 ARN을 ID 자리에 넣지 않습니다.

```text
python -m lab.cli check
```

**확인:** KB가 ACTIVE이고 데이터 소스·역할·임베딩·인덱스·원본 경로가 준비한 구성과 일치해야 합니다.

### 7-5. Sync 실행

```text
python -m lab.cli sync --apply
```

**확인:** 수집 완료 상태와 실패 문서 수 0을 확인합니다. 콘솔에서 Sync를 눌렀다면 CLI 작업을 동시에 시작하지 않습니다. 코드가 4분 후 대기를 중단해도 수집을 취소한 것은 아니므로 콘솔에서 기존 작업을 먼저 확인합니다.

### 7-6. 생성 없이 원문 검색

```text
python -m lab.cli retrieve "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3
python -m lab.cli retrieve "CloudShelf 보고서 제출 마감과 제출 폴더는 무엇인가?" --top-k 3
```

**확인:** 실제 검색 조각의 text, doc_id, S3 위치를 로컬 원문과 대조합니다. 질문에 필요한 정보가 있는지 직접 읽습니다. 이 명령은 Retrieve만 호출하며 생성 모델은 호출하지 않습니다. 검색 score는 정답 확률이 아닙니다.

완료 체크:

- [ ] S3의 두 원본 객체를 확인했다.
- [ ] KB가 준비한 역할과 인덱스를 사용한다.
- [ ] Sync 완료와 실패 문서 수를 확인했다.
- [ ] 검색 원문과 doc_id, 출처 위치를 확인했다.

보고서에 답할 질문:

1. 일반 S3와 S3 Vectors는 각각 무엇을 저장하나요?
2. S3에 파일을 올린 뒤 Sync가 필요한 이유는 무엇인가요?
3. 임베딩 모델과 생성 모델의 역할은 어떻게 다른가요?
4. 검색 결과가 반환됐다는 사실만으로 질문의 정답 근거를 찾았다고 할 수 있나요?

## 8. Assignment 3: 검색한 근거로 답변하기

**목표:** 검색 원문이 생성 모델의 실제 입력에 추가되는 것을 확인하고, 답변을 근거와 대조합니다.

### 8-1. 같은 질문을 RAG로 실행

```text
python -m lab.cli rag "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3 --max-tokens 256
```

Assignment 1의 문서 미제공 질문과 비교합니다. 모델·system prompt·출력 상한·temperature는 같고, RAG에서는 검색한 원문이 입력에 추가됩니다. 입력 토큰 수는 달라질 수 있습니다.

| 결과 필드 | 확인할 것 |
|---|---|
| retrieval_request | 검색 질문·최대 결과 수·doc_id 필터 |
| evidence | 실제 검색 원문 |
| request.messages | 생성 모델에 전달한 질문과 원문 텍스트 |
| answer | 검색 근거를 참고한 실제 답변 |
| usage / stop_reason | 실제 생성 사용량·종료 사유 |
| calls | 앱이 수행한 검색·생성 호출 수 |

검색 근거가 없으면 앱이 생성을 생략합니다. 이 경우 Converse 요청이 없으므로 request.messages도 생성 입력으로 해석하지 않습니다. 실제 결과 상태를 먼저 확인합니다.

**확인:** 문서 원문이 실제 생성 입력에 포함됐는지, 답변의 중요한 문장이 그 원문과 일치하는지 판단합니다. D1 같은 표시는 앱의 근거 번호이며 사실성 검증 완료를 뜻하지 않습니다.

### 8-2. 문서에 없는 질문

```text
python -m lab.cli rag "CloudShelf 동아리 회비는 얼마인가?" --top-k 3 --max-tokens 256
```

문서에는 회비가 없습니다. 관련 문단이 반환될 수도 있지만, 그것이 회비의 정답 근거라는 뜻은 아닙니다. 답변이 확인할 수 없음을 밝히는지, 임의 금액을 만드는지 기록합니다.

### 8-3. 검색 개수만 바꾸기

```text
python -m lab.cli rag "CloudShelf 실습 코드와 제출 마감, 제출 폴더를 함께 알려 줘." --top-k 1 --max-tokens 256
python -m lab.cli rag "CloudShelf 실습 코드와 제출 마감, 제출 폴더를 함께 알려 줘." --top-k 3 --max-tokens 256
```

질문·문서·생성 설정을 유지하고 최대 결과 수만 바꿉니다. 실제 반환 수와 필요한 근거, 입력 토큰과 답변 차이를 기록합니다. 문서가 짧거나 조각이 적으면 결과가 같을 수 있습니다. 더 많이 검색하면 항상 더 정확해진다고 결론 내리지 않습니다.

### 8-4. 선택 과제: 문서 업데이트

진행자의 안내에 따라 data/lab-guide.txt 첫 번째 절의 CLOUD-RAG-27만 CLOUD-RAG-28로 바꿉니다. doc_id와 다른 문장은 유지합니다.

```text
python -m lab.cli upload --apply
python -m lab.cli sync --apply
python -m lab.cli retrieve "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3
python -m lab.cli rag "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3 --max-tokens 256
```

원문과 답변에 새 코드가 반영됐는지 확인합니다. 즉시 반영되지 않으면 기존 Sync 상태와 검색 반영 지연을 먼저 확인합니다. 원본과 검색 인덱스를 업데이트한 것이며 생성 모델을 추가 학습한 것은 아닙니다.

완료 체크:

- [ ] 직접 호출과 RAG의 실제 입력·답변을 비교했다.
- [ ] 문서에 없는 정보의 처리 결과를 확인했다.
- [ ] top-k 1과 3에서 실제 반환 수·근거·토큰·답변을 기록했다.
- [ ] 선택 과제를 했다면 변경 전후 원문과 Sync 상태를 남겼다.

보고서에 답할 질문:

1. 직접 호출과 RAG에서 실제 생성 입력은 무엇이 달라졌나요?
2. 출처 표시가 있어도 답변의 사실 여부를 확인해야 하는 이유는 무엇인가요?
3. top-k를 늘렸을 때 이번 결과는 어떻게 달라졌나요? 차이가 없다면 그 사실과 가능한 이유를 기록하세요.
4. 선택 과제의 문서 업데이트는 모델 추가 학습과 어떻게 다른가요?

## 9. 제출물

ZIP의 templates/report.md를 복사해 작성합니다. 별도 제출 위치·마감은 실제 수업의 진행자 공지를 따릅니다. 가상 문서에 적힌 마감과 제출 경로를 실제 과제 공지로 사용하지 않습니다.

필수 내용:

1. maxTokens 64·256에서 실제 입력·출력 토큰과 stop_reason 비교
2. Sync 완료 상태·실패 문서 수·실제 검색 근거
3. 문서 미제공 직접 호출과 RAG의 실제 입력·답변 차이
4. 문서에 없는 회비 질문에 대한 답변과 판단
5. top-k 1·3에서 반환 수·근거·입력 토큰·답변의 차이
6. Converse·Retrieve·Sync·생성 모델·임베딩 모델의 역할 설명
7. 비용 항목·사용자와 서비스 역할의 차이·자원 정리 결과

개선되지 않았거나 결과가 같아도 그대로 설명합니다. 권한·호출 오류는 품질 평가와 따로 기록합니다. 비밀키·토큰·개인 설정·계정 ID 전체를 제출하지 않습니다.

### 보고서 기록표

아래 표는 기록 항목을 보여 주는 양식입니다. 예측한 값이 아니라 **본인이 실행한 실제 결과**로 채웁니다. 전체 보고서 양식은 ZIP의 templates/report.md를 사용합니다.

**실행 환경:** 작성자 / 실행 날짜 / OS / Python·AWS CLI 버전 / 리전 / 생성 모델 / 임베딩 모델·차원

| Assignment 1 | 실제 inputTokens | 실제 outputTokens | stop_reason | 답변에서 관찰한 점 |
|---|---|---|---|---|
| 출력 상한 64 | | | | |
| 출력 상한 256 | | | | |

**Assignment 2:** Sync 상태 / 실패 문서 수 / 검색 원문 발췌 / doc_id / 출처 위치 / 원문과의 일치 여부

| Assignment 3 | 실제 입력에 추가된 문서 | 답변의 핵심 내용 | 원문으로 뒷받침되는가? |
|---|---|---|---|
| 문서 미제공 직접 호출 | | | |
| 같은 질문의 RAG | | | |
| 문서에 없는 회비 질문 | | | |

| 검색 개수 비교 | 실제 반환 수 | 필요한 근거 포함 여부 | 실제 입력 토큰 | 답변의 차이 |
|---|---|---|---|---|
| top-k 1 | | | | |
| top-k 3 | | | | |

**마무리:** 사용한 서비스의 역할 / 비용 항목 / 사용자와 KB 서비스 역할의 차이 / 전용 자원 정리 결과 / 배운 점

### 제출 확인

- [ ] 실행 결과와 검색 원문에 근거해 설명했다.
- [ ] 결과가 같거나 기대와 달랐던 경우도 그대로 기록했다.
- [ ] 비밀키·로그인 토큰·개인 설정 파일을 제외했다.
- [ ] 실제 제출 위치·마감은 진행자의 공지를 확인했다.
- [ ] 다음 절에 따라 실습 자원을 정리했다.

## 10. 실습 전용 자원 정리

```text
python -m lab.cli plan
```

자신의 계정·suffix 자원 이름을 대조한 뒤 콘솔에서 순서대로 확인합니다.

1. 수집 작업이 진행 중인지 확인합니다.
2. 실습 데이터 소스의 삭제 정책을 확인하고 데이터 소스·KB를 정리합니다.
3. 본인 S3 Vectors 버킷의 documents 인덱스와 벡터 버킷을 정리합니다.
4. 일반 S3의 docs/ 원본 두 객체를 정리하고 빈 버킷을 삭제합니다. 버전 관리를 별도로 켰다면 이전 버전과 삭제 마커도 확인합니다.
5. 실습용 KeulkeulBedrockKB-suffix 역할의 전용 정책과 역할을 정리합니다.
6. 이번 과제의 고객 관리형 정책 01~04는 관리자가 연결 해제·정리합니다.
7. 남은 자원과 사용량·청구를 확인합니다. 청구 반영에는 지연이 있을 수 있습니다.

공유 자원과 다른 실습의 정책은 정리 대상이 아닙니다. KB 삭제만으로 연결한 저장소가 모두 삭제됐다고 가정하지 않습니다. 이 패키지는 자동 삭제를 실행하지 않습니다.

## 11. 막혔을 때 확인할 것

| 증상 | 확인·조치 |
|---|---|
| No module named lab | 현재 폴더에 lab과 setup.ps1이 있는지 확인 |
| boto3 모듈을 찾지 못함 | 가상환경 Python 경로와 setup 설치 결과 확인 |
| aws 명령이 없음 / login을 모름 | AWS CLI 설치 후 새 터미널, 버전 2.32.0 이상 확인 |
| 로그인 만료 | aws login 또는 해당 SSO 로그인 재실행 |
| 계정 불일치·root 차단 | STS와 config의 계정·IAM 신원 확인 |
| 직접 정책 연결에 정책이 안 보임 | 관리자가 해당 계정에 고객 관리형 정책을 생성했는지, 필터·검색어 확인 |
| JSON 길이 한도 | 고객 관리형 정책 4개를 각각 생성했는지 확인. 인라인에 합치지 않음 |
| AccessDenied | 오류의 작업·자원·실행 주체를 확인해 관리자에게 전달. 임의로 전체 관리자 권한을 붙이지 않음 |
| CreateIndex에서 권한 없음 | 수정된 01 정책에서 CreateIndex가 인덱스 ARN에 허용되는지, AWS의 기본 정책 버전과 실습 사용자 연결 상태 확인 |
| 모델·프로파일 호출 오류 | 리전·model_id·모델 접근·프로파일과 대상 리전 권한 확인 |
| 자원 이름이 이미 존재함 | 기존 자원을 인수하지 말고 진행자와 확인. 새 실습은 새 폴더·새 suffix 사용 |
| KB 연결 검사 실패 | 실제 ID, 역할, docs/ 경로, Titan 모델과 1024차원, documents 인덱스 확인 |
| 검색 결과 없음·doc_id 오류 | 원본 두 객체, metadata 파일명·doc_id, 데이터 소스 경로, Sync 실패 수 확인 |
| 이전 코드가 검색됨 | 로컬 수정만 하지 않았는지, 재업로드·Sync·검색 반영 상태 확인 |
| 답변은 나왔는데 틀림 | 필요한 원문이 검색됐는지 확인한 뒤 답변의 주장과 대조 |

오류를 공유할 때는 질문·실행 단계·오류 코드와 필요한 설정 이름만 전달합니다. 액세스 키나 로그인 토큰은 보내지 않습니다.

## 12. 검증 범위와 공식 참고

제작 시 Windows Python 3.11에서 AWS 호출 없는 로컬 테스트 18개와 가짜 클라이언트 기반 CLI 결과 저장을 확인했습니다. CreateIndex 권한의 인덱스 ARN 범위를 검사하는 테스트를 포함합니다. 실제 AWS 로그인·권한 적용·자원 생성·수집·검색·모델 호출·삭제, 응답 품질·시간·비용은 진행자가 리허설로 확인해야 합니다. Mac 실제 실행도 별도 확인 대상입니다.

정확한 토큰 수·응답 문장·검색 조각 수·비용·시간을 미리 정답처럼 제공하지 않습니다. 콘솔 UI가 바뀌면 공식 문서와 리허설 기록을 기준으로 안내를 갱신합니다.

- [AWS CLI 브라우저 로그인](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)
- [Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [벡터 저장소 연결형 KB 생성](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-create.html)
- [S3 데이터 소스](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html)
- [검색 설정](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- [KB 서비스 역할](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-permissions.html)
- [Nova Lite와 지원 리전](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html)
- [IAM 정책 한도](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html)
- [S3 Vectors 작업별 권한·자원 범위](https://docs.aws.amazon.com/service-authorization/latest/reference/list_s3vectors.html)
- [Bedrock 요금](https://aws.amazon.com/bedrock/pricing/), [S3 요금](https://aws.amazon.com/s3/pricing/)
