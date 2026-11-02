# Amazon Bedrock 실습 · 처음 시작하는 순서

실습 흐름은 **사전 준비 → Assignment 1 모델 호출 → Assignment 2 문서 수집·검색 → Assignment 3 RAG 비교 → 제출·정리**입니다.

실행 파일은 이 저장소의 `assignment/week17-bedrock` 폴더에 있습니다. 저장소를 clone하거나 **Code → Download ZIP**으로 내려받아 압축을 푼 뒤 이 폴더를 사용합니다. 모든 명령은 해당 폴더에서 실행합니다. 코드 블록의 명령만 복사하며, 앞뒤의 백틱 표시나 PowerShell의 `PS ...>` 프롬프트는 입력하지 않습니다.

## 사전 준비

### 1. 새 실습 폴더 열기

저장소를 받은 뒤 `assignment/week17-bedrock`으로 이동합니다. `setup.ps1`, `requirements.txt`, `lab`, `data`가 함께 들어 있는 폴더에서 PowerShell을 엽니다. 예를 들어 문서 폴더에 압축을 풀었다면 실제 폴더 경로로 먼저 이동합니다.

```powershell
Get-Location
Get-ChildItem
```

목록에 `setup.ps1`이 보이면 올바른 실행 위치입니다. 다른 실습의 `config.json`, `.local`, `iam/generated`, 결과 폴더를 복사하지 않습니다.

### 2. 실행 환경 설치

Windows 기준입니다. Mac 준비 명령은 `00-prerequisites.md`를 확인합니다.

```powershell
py -3.11 --version
aws --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
$env:Path = (Join-Path (Get-Location) ".venv\Scripts") + ";" + $env:Path
python -c "import sys; print(sys.executable)"
python -m pip check
python -m lab.cli --help
```

확인: Python 경로가 현재 실습 폴더의 `.venv\Scripts\python.exe`로 끝나고, 설치 오류 없이 CLI 명령 목록이 나와야 합니다. 설치가 실패했다면 다음 단계로 넘어가지 않습니다. PATH 설정은 현재 PowerShell 창에서만 적용됩니다.

### 3. 개인 설정과 정책 파일 생성

아래 계정 ID는 예시입니다. 자신의 AWS 계정 ID로 바꿔 실행합니다. `student01`은 본인의 실습 자원을 구분하는 suffix입니다. 같은 계정에서 여러 명이 실습하면 서로 다른 suffix를 정합니다.

```text
python -m lab.cli init --account 123456789012 --suffix student01 --profile keulkeul-bedrock
```

확인: `config.json`과 `iam/generated`가 생성됩니다. 이 단계는 PC에 파일만 만들며 AWS 자원은 생성하지 않습니다. `knowledge_base_id`, `data_source_id`는 이때 빈 문자열로 둡니다. 이전 프로젝트의 KB ID를 넣지 않습니다.

### 4. 관리자: IAM 정책 4개 생성·연결

Windows에서는 생성된 파일을 다음 명령으로 엽니다.

```powershell
explorer .\iam\generated
notepad .\iam\generated\01-storage-setup.json
```

IAM 권한을 관리할 수 있는 사람이 **IAM → 정책 → 정책 생성 → JSON**에서 파일의 전체 내용을 붙여 넣어 고객 관리형 정책을 각각 만듭니다.

| 파일 | 정책 이름 예시 |
|---|---|
| 01-storage-setup.json | KeulkeulBedrock-student01-Storage |
| 02-role-setup.json | KeulkeulBedrock-student01-RoleSetup |
| 03-kb-setup.json | KeulkeulBedrock-student01-KBSetup |
| 04-app-runtime.json | KeulkeulBedrock-student01-Runtime |

파일 앞의 01~04는 파일 번호입니다. **한 사람이 사용하는 계정·suffix는 네 정책 모두 동일하게 유지**합니다. 정책 네 개를 하나의 사용자 인라인 정책으로 합치지 않습니다.

관리자는 **IAM → 사용자 → 실습 사용자 → 권한 추가 → 정책 직접 연결**에서 네 정책을 연결합니다. 브라우저 기반 `aws login`을 사용하려면 AWS 관리형 `SignInLocalDevelopmentAccess`도 허용되어 있어야 합니다. 기존 허용이 있다면 중복 추가할 필요는 없습니다.

`kb-service-trust.json`과 `kb-service-access.json`은 사용자에게 연결하지 않습니다. 이 두 정책은 Assignment 2에서 KB 서비스 역할을 준비하는 데 사용합니다. **지금은 KB 서비스 역할이 없어도 됩니다.**

최신 배포본은 CreateIndex 권한이 수정되어 있습니다. 새로 시작하는 참가자는 이전 정책 교체 절차를 수행하지 않고 이 단계에서 수정된 정책을 처음부터 생성합니다. 조직 SSO를 이미 사용하는 참가자의 권한 적용은 관리자가 진행합니다.

### 5. 실습 사용자로 로그인

IAM 사용자 방식의 기본 경로입니다.

```text
aws login --profile keulkeul-bedrock
```

리전을 물으면 `ap-northeast-2`를 입력합니다. 브라우저에서 실습용 IAM 사용자·역할로 로그인하고 로컬 개발 접근을 승인합니다.

```text
aws sts get-caller-identity --profile keulkeul-bedrock
```

확인: 로그인 계정이 `config.json`의 계정 ID와 같고 실습용 사용자·역할이어야 합니다. 루트 신원으로 실습 프로그램을 실행하지 않습니다. IAM 사용자 방식에서는 `aws configure sso`와 `aws sso login`을 추가로 실행하지 않습니다. SSO 환경은 `00-prerequisites.md`의 별도 경로를 사용합니다.

## Assignment 1 · 모델을 직접 호출하고 응답 읽기

### 1. 출력 상한 비교

```text
python -m lab.cli generate "Amazon S3와 Bedrock Knowledge Bases의 역할을 초보자에게 단계별로 자세히 설명해 줘." --max-tokens 64 --temperature 0
python -m lab.cli generate "Amazon S3와 Bedrock Knowledge Bases의 역할을 초보자에게 단계별로 자세히 설명해 줘." --max-tokens 256 --temperature 0
```

두 결과의 실제 `usage`, `stop_reason`, 답변을 기록합니다. 출력 상한은 글자 수나 반드시 채워야 하는 길이가 아닙니다. `max_tokens`로 종료되면 출력 상한에 도달해 중단된 것입니다. 256에서도 긴 답변은 중간에 끊길 수 있습니다.

`retrieve: 0`, `converse: 1`은 문서 검색 없이 생성 모델을 한 번 호출했다는 뜻입니다. `invalid_citations`가 나오면 실제 제공하지 않은 출처 번호를 생성했는지 확인해 기록합니다. 답변 생성 성공과 근거의 유효성은 구분합니다.

### 2. 문서를 주지 않은 질문

```text
python -m lab.cli generate "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --max-tokens 256
```

아직 로컬 TXT나 KB를 연결하지 않았습니다. 알 수 없다고 답하는지, 특정 값을 추측하는지 관찰합니다. 결과는 `outputs/generate-실행시각`에 저장되며 Assignment 3에서 비교합니다.

완료: 두 출력 상한의 실제 토큰·종료 사유와 문서 미제공 질문의 답변을 보관합니다.

## Assignment 2 · 문서를 수집하고 원문 검색하기

### 1. 원본과 metadata 확인

```powershell
notepad .\data\lab-guide.txt
notepad .\data\lab-guide.txt.metadata.json
```

TXT에서 가상 실습 코드·마감·제출 폴더를 확인합니다. metadata에서 `doc_id`가 `lab-guide-v1`인지 확인합니다. 이번 단계에서는 두 파일을 읽기만 합니다. 실제 동아리 규정이나 제출 공지가 아닙니다.

### 2. 저장소·인덱스·역할 준비

```text
python -m lab.cli plan
```

자신의 계정·서울 리전·suffix와 `documents` 인덱스를 사용할 계획인지 확인한 뒤 실행합니다.

```text
python -m lab.cli prepare --apply
```

이 명령이 일반 S3, S3 Vectors 버킷과 1024차원 `documents` 인덱스, `KeulkeulBedrockKB-본인suffix` 역할을 생성합니다. Knowledge Base 자체는 아직 생성하지 않습니다.

**확인:** 오류 없이 `준비 완료`가 나와야 합니다. IAM → 역할에서 위 역할이 확인되어야 합니다. 권한 오류가 나면 사전 준비의 정책 연결부터 확인하고 해결 후 같은 명령을 다시 실행합니다. 오류가 있는 상태로 다음 단계에 넘어가지 않습니다.

### 3. 문서 업로드

```text
python -m lab.cli upload --apply
```

확인: 일반 S3의 `docs/` 아래 TXT와 metadata 두 객체가 있어야 합니다. `검색 반영에는 Sync가 필요합니다`는 다음 작업 안내이며 업로드 실패가 아닙니다.

### 4. 콘솔에서 이번 실습용 Knowledge Base 생성

서울 리전의 Bedrock 콘솔에서 **Knowledge bases → Create → Knowledge base with a vector store**를 선택합니다.

| 항목 | 값 |
|---|---|
| KB 이름 | keulkeul-bedrock-본인suffix |
| 서비스 역할 | 기존 역할 사용: KeulkeulBedrockKB-본인suffix |
| 데이터 소스 | Amazon S3 |
| 원본 경로 | 자신의 일반 S3 버킷의 docs/ |
| 파서 | 기본 파서 |
| 청킹 | Fixed-size, 300토큰, 겹침 20% |
| 임베딩 모델 | Titan Text Embeddings V2 |
| 벡터 형식·차원 | float32, 1024 |
| 벡터 저장소 | 기존 저장소 사용 → Amazon S3 Vectors |
| 연결 인덱스 | plan에 표시된 index_arn, 본인 실습 버킷의 documents |
| 데이터 삭제 정책 | 실습 전용 인덱스의 DELETE |

Quick create로 별도 저장소를 추가하지 않습니다. 기존 연구용 KB의 `papers` 인덱스를 선택하지 않습니다. IAM 역할과 인덱스가 없다면 앞의 prepare를 완료했는지 확인합니다.

### 5. 새 KB ID와 데이터 소스 ID 입력·검사

이번에 생성한 KB의 **Knowledge Base ID**와 그 안에 연결된 S3의 **Data source ID**를 각각 확인합니다.

```powershell
notepad .\config.json
```

`knowledge_base_id`와 `data_source_id`의 빈 문자열에 각각 실제 ID를 넣고 저장합니다. 이름이나 ARN을 넣지 않고, 다른 프로젝트의 ID를 가져오지 않습니다. 파일 전체를 두 항목만 있는 JSON으로 바꾸지 않습니다.

```text
python -m lab.cli check
```

확인: ACTIVE 상태와 데이터 소스·역할·임베딩·인덱스·S3 원본 경로 검사가 통과해야 합니다. 인덱스가 다르다는 오류는 ID가 저장되지 않았다는 뜻이 아니라 다른 구성이 연결되었다는 뜻입니다.

### 6. Sync

```text
python -m lab.cli sync --apply
```

수집 완료와 실패 문서 수 0을 확인합니다. 대기 시간이 초과되면 기존 수집 작업을 콘솔에서 확인하고, 작업이 진행 중인 동안 중복 실행하지 않습니다.

### 7. 원문 검색

```text
python -m lab.cli retrieve "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3
python -m lab.cli retrieve "CloudShelf 보고서 제출 마감과 제출 폴더는 무엇인가?" --top-k 3
```

검색된 원문·doc_id·출처를 로컬 TXT와 대조합니다. Retrieve는 생성 답변을 만드는 단계가 아닙니다.

완료: Sync 결과와 실제 검색 원문, 각 서비스의 역할을 기록합니다.

## Assignment 3 · 검색 근거를 활용해 답변하고 비교하기

### 1. 같은 질문을 RAG로 실행

```text
python -m lab.cli rag "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3 --max-tokens 256
```

Assignment 1의 답변과 비교합니다. `result.json`의 `evidence`와 `request.messages`에 실제 검색 원문이 추가되었는지 확인합니다. 생성 모델에 제공하는 것은 검색 원문의 텍스트입니다.

### 2. 문서에 없는 질문

```text
python -m lab.cli rag "CloudShelf 동아리 회비는 얼마인가?" --top-k 3 --max-tokens 256
```

검색 결과가 있어도 회비를 뒷받침하는 근거인지는 별도로 판단합니다. 확인할 수 없다고 답하는지, 근거 없는 금액을 만드는지 원문과 대조합니다.

### 3. 검색 개수 비교

```text
python -m lab.cli rag "CloudShelf 실습 코드와 제출 마감, 제출 폴더를 함께 알려 줘." --top-k 1 --max-tokens 256
python -m lab.cli rag "CloudShelf 실습 코드와 제출 마감, 제출 폴더를 함께 알려 줘." --top-k 3 --max-tokens 256
```

실제 반환 수·필요한 근거·입력 토큰·답변을 비교합니다. 짧은 문서라 결과가 같을 수 있으며, 더 많이 검색하면 항상 더 정확하다고 결론 내리지 않습니다.

### 4. 선택: 문서 수정 후 재동기화

`data/lab-guide.txt` 첫 번째 절의 코드만 `CLOUD-RAG-27`에서 `CLOUD-RAG-28`로 바꿉니다. 다른 내용과 doc_id는 유지합니다.

```text
python -m lab.cli upload --apply
python -m lab.cli sync --apply
python -m lab.cli retrieve "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3
python -m lab.cli rag "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3 --max-tokens 256
```

새 값이 검색 원문과 답변에 반영되는지 확인합니다. 이는 원본과 검색 인덱스 업데이트이며 생성 모델을 추가 학습한 것이 아닙니다.

완료: 직접 호출/RAG, 문서에 없는 질문, top-k 비교를 실제 입력과 원문에 근거해 설명합니다.

## 제출과 자원 정리

1. `templates/report.md`를 복사해 실제 결과로 작성합니다. 질문·요청·원문·답변·토큰·종료 사유와 서비스 역할을 포함합니다.
2. `04-cleanup.md`를 따라 실습 KB·데이터 소스 → 벡터 인덱스·버킷 → 일반 S3 객체·버킷 → 전용 역할·정책 순으로 정리합니다. 공용 로그인 정책과 다른 프로젝트는 대상이 아닙니다.
3. 실제 제출 위치와 마감은 진행자 공지를 따릅니다. TXT의 가상 일정과 제출 폴더를 실제 공지로 사용하지 않습니다.

기준 리전은 서울입니다. Nova Lite APAC 추론은 서울 외 지원 리전에서 처리될 수 있습니다. 모델·임베딩·저장·검색 비용이 발생할 수 있습니다. 정확한 응답·실행 시간·비용을 미리 정답으로 제공하지 않습니다.

검증 상태: 로컬 테스트 18개와 배포 파일 검사를 완료했습니다. 실제 AWS 전체 실습은 진행자가 새 환경에서 리허설해야 합니다. 이번 초기화 작업은 실습 전체 완주 검증을 뜻하지 않습니다.

공식 참고: [KB 생성](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-create.html), [CLI 로그인](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html), [S3 Vectors 권한](https://docs.aws.amazon.com/service-authorization/latest/reference/list_s3vectors.html).
