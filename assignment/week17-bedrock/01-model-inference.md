# Assignment 1 · Bedrock 모델을 직접 호출하고 응답 읽기

## 목표

Knowledge Base를 만들기 전에 생성 모델을 API로 호출한다. `modelId`, `messages`, `inferenceConfig`와 응답의 본문·`usage`·`stopReason`을 구분한다.

[사전 준비](00-prerequisites.md)를 완료한 뒤 실습 폴더의 가상환경 Python을 사용한다. 생성 모델 호출이 가능한 정책·프로필이 필요하며 이 단계는 KB ID가 비어 있어도 실행된다.

## 1. 같은 질문, 다른 출력 상한

```text
python -m lab.cli generate "Amazon S3와 Bedrock Knowledge Bases의 역할을 초보자에게 단계별로 자세히 설명해 줘." --max-tokens 64 --temperature 0
python -m lab.cli generate "Amazon S3와 Bedrock Knowledge Bases의 역할을 초보자에게 단계별로 자세히 설명해 줘." --max-tokens 256 --temperature 0
```

각 명령은 Converse 한 번을 호출하며 `outputs/generate-실행시각/`에 `result.json`과 `result.md`를 저장한다. 재시도·재실행으로 실제 과금 요청 수는 늘 수 있다.

JSON에서 확인할 필드:

| 필드 | 확인할 것 |
|---|---|
| `request.modelId` | 호출한 생성 모델/추론 프로파일 |
| `request.messages` | 모델에게 보낸 실제 질문·evidence 입력 |
| `request.inferenceConfig` | `maxTokens`와 `temperature` |
| `answer` | 반환된 텍스트 |
| `usage` | 실제 API 응답의 inputTokens·outputTokens 등 |
| `stop_reason` | 실제 `stopReason`. 예: end_turn, max_tokens |

`maxTokens=64`는 정확히 64토큰이나 64글자를 생성하라는 뜻이 아니라 최대 출력 토큰 수다. 더 일찍 끝날 수 있다. `stopReason`이 `max_tokens`라면 상한 때문에 중단됐는지 답변 내용과 함께 본다. 64에서 반드시 잘리거나 256에서 반드시 완성된다는 결과를 미리 정하지 않는다.

temperature는 출력의 선택 경향에 영향을 주는 설정이다. 낮춘다고 정답률이 보장되거나 출력이 완전히 같아지는 것은 아니다. 필수 비교에서는 출력 상한만 바꾼다.

## 2. 아직 문서를 주지 않은 질문

다음 질문을 그대로 실행하고 결과를 보존한다. 아직 TXT 내용이나 정답을 프롬프트에 추가하지 않는다.

```text
python -m lab.cli generate "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --max-tokens 256
```

이때 CLI는 로컬 `lab-guide.txt`를 읽거나 KB 검색을 하지 않는다. `request.messages`의 evidence가 빈 목록인지 확인한다. 모델이 알 수 없다고 답하는지, 구체적인 값을 추측하는지 관찰한다. 정답을 맞혔더라도 문서가 자동 연결됐다고 판단하지 않는다. 이 실습은 정보 전달 경로를 확인하며 통계적인 모델 성능 평가를 하지 않는다.

## 완료·제출

- 두 출력 상한에서 실제 usage·stopReason과 답변 차이를 기록한다.
- 입력 토큰과 출력 토큰의 차이를 설명한다.
- 모델 직접 호출에는 문서 검색이나 KB ID가 필요하지 않았다는 점을 설명한다.
- 문서 미제공 질문의 결과 폴더를 Assignment 3 비교용으로 남긴다.

다음: [Assignment 2](02-knowledge-base.md)
