# Assignment 2 · 문서 수집과 원문 검색

[← Assignment 1](assignment1.md) · [Assignment 3 →](assignment3.md)

**목표:** 원본 저장, 문서 인덱싱, 원문 검색을 구분합니다. 생성 답변을 만들기 전에 검색된 자료부터 확인합니다.

## 1. 문서와 메타데이터 확인

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

## 2. 생성 계획 확인 후 저장소·역할 준비

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

### 실행 전: 이번 실습용 KB ID인지 확인

처음 진행하여 이번 실습용 Knowledge Base가 아직 없다면 config.json의 **knowledge_base_id와 data_source_id는 모두 빈 문자열 `""`**이어야 합니다. 이름이 비슷하더라도 다른 프로젝트의 KB ID를 넣지 않습니다.

다른 프로젝트의 ID를 이미 입력했다면 Windows에서는 아래 명령으로 파일을 열고 **이 두 항목의 값만** 빈 문자열로 바꿔 저장합니다. Mac에서는 config.json을 편집기로 엽니다. 파일 전체를 두 항목만 있는 JSON으로 덮어쓰지 않습니다.

```powershell
notepad .\config.json
```

이 두 ID는 뒤의 콘솔 단계에서 **이번 실습의 documents 인덱스에 연결된 KB와 데이터 소스**를 만든 후 입력합니다. 이미 올바른 실습 KB를 생성한 참가자는 다른 프로젝트의 ID와 혼동하지 않도록 확인합니다.

### 저장소와 역할 생성

```text
python -m lab.cli prepare --apply
```

이 도구는 저장소와 서비스 역할을 준비합니다. **Knowledge Base 자체는 다음 단계에서 콘솔로 직접 연결합니다.** 일반 S3의 퍼블릭 액세스 차단과 벡터 인덱스의 차원을 확인합니다.

중간 실패는 .local/storage-state.json에 기록됩니다. 원인을 해결한 뒤 같은 설정으로 재실행합니다. 상태 파일을 지우고 기존 자원을 임의로 인수하거나 삭제하지 않습니다.

### CreateIndex 권한 오류가 발생한 경우

오류에 **AccessDeniedException / s3vectors:CreateIndex / no identity-based policy allows**가 표시되면 인덱스 생성 권한을 확인합니다. 이 단계에서 중단되면 그 뒤에 생성하는 KB 서비스 역할도 아직 없을 수 있습니다.

1. [README](README.md)의 **4-2. 이전 정책을 이미 생성한 경우**에 따라 수정된 01-storage-setup.json으로 AWS의 Storage 고객 관리형 정책을 업데이트합니다.
2. 정책의 기본 버전, 실습 사용자 연결 상태, 대상 인덱스 ARN이 본인의 실습 자원과 일치하는지 확인합니다.
3. 권한을 수정한 뒤 **같은 폴더·계정·suffix**로 아래 명령을 다시 실행합니다.

```text
python -m lab.cli prepare --apply
```

이미 완료 기록이 있는 버킷 생성 단계는 건너뛰고 벡터 인덱스와 서비스 역할 준비를 이어갑니다. 오류가 계속되면 오류 메시지와 정책 연결 상태를 진행자에게 전달합니다. 오류가 남아 있는 상태에서 업로드나 KB 연결 단계로 넘어가지 않습니다.

### 다음 단계로 넘어가기 전 확인

- [ ] prepare가 오류 없이 끝나고 **준비 완료** 메시지가 나왔다.
- [ ] S3 Vectors에 본인 실습 버킷의 **documents 인덱스, 1024차원**이 준비됐다.
- [ ] **IAM → 역할**에서 **KeulkeulBedrockKB-본인suffix**가 확인된다. 이 역할을 콘솔의 KB 생성 화면에서 기존 서비스 역할로 선택한다.

여기까지는 저장소와 권한을 준비한 상태입니다. Knowledge Base 자체는 아래의 **AWS 콘솔에서 Knowledge Base 연결** 단계에서 새로 만듭니다.

## 3. TXT와 metadata 업로드

```text
python -m lab.cli upload --apply
```

**확인:** 일반 S3의 docs/ 아래에 lab-guide.txt와 lab-guide.txt.metadata.json, 총 두 객체가 있어야 합니다. 아직 검색 인덱스에 반영된 상태는 아닙니다.

## 4. AWS 콘솔에서 Knowledge Base 연결

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

## 5. Sync 실행

```text
python -m lab.cli sync --apply
```

**확인:** 수집 완료 상태와 실패 문서 수 0을 확인합니다. 콘솔에서 Sync를 눌렀다면 CLI 작업을 동시에 시작하지 않습니다. 코드가 4분 후 대기를 중단해도 수집을 취소한 것은 아니므로 콘솔에서 기존 작업을 먼저 확인합니다.

## 6. 생성 없이 원문 검색

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
