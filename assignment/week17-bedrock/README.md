# Week 17 · Amazon Bedrock 기본 기능과 Knowledge Bases 실습

처음 시작할 때는 [처음부터 실습 순서](START_HERE.md)를 위에서부터 진행합니다. 개인 설정·상태 파일·실행 결과를 제외한 공통 실습 코드입니다.

**모델 직접 호출, 문서 수집·검색, 검색 근거를 활용한 생성 과정을 구분해서 이해한다.** 논문 비교 서비스 개발 대신 Bedrock API와 Knowledge Bases의 동작을 확인하는 공통 실습이다.

처음 참가하는 사람은 [참가자용 통합 실행 안내](NOTION_GUIDE.md)를 위에서부터 따라갑니다. 설치·계정·정책·실행 명령·확인 기준·오류 해결·정리까지 한 파일로 연결합니다.

## 진행 순서

| 단계 | 안내 | 완료 기준 |
|---|---|---|
| 사전 준비 | [계정·설치·IAM](00-prerequisites.md) | 실행 계정·프로필·정책 준비 |
| Assignment 1 | [모델 직접 호출](01-model-inference.md) | Converse 요청·응답·usage·stopReason 이해 |
| Assignment 2 | [문서 수집과 검색](02-knowledge-base.md) | Sync 후 실제 원문·metadata·위치 확인 |
| Assignment 3 | [문서 근거로 답변하기](03-rag.md) | 직접 호출/RAG 차이와 검색 개수 변경 관찰 |
| 마무리 | [자원 정리](04-cleanup.md) | 실습 전용 자원 확인·정리 |
| 제출 | [보고서 양식](templates/report.md) | API와 데이터 흐름을 자신의 말로 설명 |

공통 자료는 `data/lab-guide.txt`다. **실제 동아리 규정이 아닌 가상 연습 문서**이며 arXiv 다운로드나 논문 이해가 필요 없다. 문서의 고유 정보를 모델이 제공받는 과정을 관찰한다. 모델이 반드시 오답을 내도록 설계한 성능 대결이나 논문별 검색 균형 실험이 아니다.

## 구성

```text
Assignment 1: 질문 → Bedrock Converse → 답변·토큰·중단 사유
Assignment 2: TXT + metadata → S3 → KB Sync → Titan 임베딩 → S3 Vectors
              질문 → KB Retrieve → 원문·metadata·위치
Assignment 3: 질문 → Retrieve → 앱에서 근거 정리 → Converse → 답변과 근거
```

기준 리전은 서울, 임베딩은 Titan Text Embeddings V2 1024차원 float32, 생성은 Nova Lite APAC 추론 프로파일이다. APAC 추론은 서울 외 지원 리전에서 처리될 수 있다. 모델과 계정 접근은 실행 전에 확인한다. [공식 출처](SOURCES.md)를 참고한다.

## 제공 코드

- `lab/lesson.py`: 실제 Converse·Retrieve 요청, 응답 정리, 검색 원문과 생성 연결
- `lab/cli.py`: 참가자가 실행하는 명령과 JSON/Markdown 결과 저장
- `lab/documents.py`: TXT·metadata 업로드
- `lab/storage.py`: 전용 저장소·KB 역할 준비와 연결 검사·동기화
- `lab/iam.py`: 계정·전용 자원에 맞춘 고객 관리형 정책 생성

`init`, `plan`, `render-policies`는 AWS를 호출하지 않는다. `prepare/upload/sync`는 `--apply`를 붙일 때 실제로 변경한다. `generate/retrieve/rag`는 실행할 때 실제 유료 API를 호출한다. 웹앱과 DynamoDB, LangGraph, EC2는 필수 과제에 포함하지 않는다.

설치·IAM은 사전 과제로 분리한다. 본 실습은 60~90분을 준비 목표로 삼되 진행자가 리허설 시간으로 조정한다. 저장·임베딩·검색·생성 비용이 발생할 수 있다. 로컬 테스트와 실제 AWS 검증 범위는 [검증 기록](VALIDATION.md), 진행자 준비는 [INSTRUCTOR.md](INSTRUCTOR.md)에서 구분한다.

## GitHub에서 받아 실행하기

```powershell
git clone https://github.com/zero-uuuuk/KeulKeul.git
cd KeulKeul/assignment/week17-bedrock
```

Git이 없다면 저장소의 **Code → Download ZIP**을 선택해 압축을 풀고 `assignment/week17-bedrock` 폴더를 엽니다. 이 폴더에서 [START_HERE.md](START_HERE.md)의 설치와 개인 설정 생성부터 진행합니다. `python -m lab.cli`는 이 폴더의 `lab/cli.py`를 실행하는 명령입니다.

`config.json`, `iam/generated`, `.local`, `outputs`, `.venv`는 참가자가 로컬에서 생성하며 Git에 포함하지 않습니다. 생성된 IAM 정책은 관리자가 AWS에서 생성·연결해야 적용됩니다.
