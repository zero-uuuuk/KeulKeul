# Assignment 3 · 검색 근거를 모델에 전달하고 변화 관찰하기

## 목표

Retrieve와 Converse가 맡는 일을 구분하고, 앱이 검색한 원문을 생성 입력에 추가하는 구조를 확인한다. 모델 직접 호출과 RAG를 비교하되 RAG가 모든 질문에서 더 우수하다는 결론을 미리 정하지 않는다.

## 1. 같은 질문을 RAG로 실행

Assignment 1에서 문서를 주지 않고 실행한 질문을 다시 사용한다.

```text
python -m lab.cli rag "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3 --max-tokens 256
```

`result.json`에서 확인한다.

- `retrieval_request`: KB에 보낸 질문·최대 결과 수·`doc_id` 필터
- `evidence`: 실제 검색 원문
- `request.messages`: Converse에 보낸 질문과 evidence 텍스트
- `answer`, `usage`, `stop_reason`: 실제 생성 응답
- `calls`: 앱이 수행한 API 호출 수. SDK의 내부 재시도 전체 횟수를 뜻하지 않음

같은 생성 모델·system prompt·출력 상한·temperature를 사용한다. 직접 호출의 evidence는 비어 있고, RAG에서는 실제 검색 조각이 입력에 포함된다. 입력 길이는 달라진다. 이는 정보가 전달되는 구조를 확인하는 비교이며 완전히 같은 입력의 성능 대결이 아니다.

## 2. 문서에 없는 질문

```text
python -m lab.cli rag "CloudShelf 동아리 회비는 얼마인가?" --top-k 3 --max-tokens 256
```

관련 없는 문단이 검색될 수도 있다. 답변이 문서에서 확인할 수 없다고 밝히는지, 임의 금액을 만드는지 원문과 대조한다. 출처 번호가 붙었어도 사실성 검증이 완료된 것은 아니다. 결과가 없을 때 앱은 생성을 생략하지만, 결과가 있다는 이유만으로 충분한 정답 근거가 있는 것은 아니다.

## 3. 검색 개수만 바꾸기

```text
python -m lab.cli rag "CloudShelf 실습 코드와 제출 마감, 제출 폴더를 함께 알려 줘." --top-k 1 --max-tokens 256
python -m lab.cli rag "CloudShelf 실습 코드와 제출 마감, 제출 폴더를 함께 알려 줘." --top-k 3 --max-tokens 256
```

최대 결과 수만 바꾸고 나머지 조건은 유지한다. 실제 반환 수, 필요한 항목이 원문에 포함됐는지, 입력 토큰과 답변이 어떻게 달라졌는지 기록한다. 문서가 짧거나 조각 수가 적으면 결과가 같을 수 있다. 더 많이 요청하면 항상 더 정확해진다고 결론 내리지 않는다.

## 4. 문서 변경과 Sync 확인

시간이 허용되면 진행자의 안내에 따라 `data/lab-guide.txt` 첫 번째 절의 `CLOUD-RAG-27`만 `CLOUD-RAG-28`로 수정한다. 다른 문장·doc_id는 유지한다.

```text
python -m lab.cli upload --apply
python -m lab.cli sync --apply
python -m lab.cli retrieve "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3
python -m lab.cli rag "가상 운영 안내의 CloudShelf 실습 코드는 무엇인가?" --top-k 3 --max-tokens 256
```

새 코드가 실제 검색 원문과 답변에 반영됐는지 확인한다. 즉시 반영되지 않으면 기존 작업 상태·동기화·검색 반영 시간을 먼저 확인한다. 이 변경은 원본과 검색 인덱스를 업데이트하는 작업이며 생성 모델 가중치를 추가 학습시키는 작업이 아니다. 수집·추가 호출 비용이 발생할 수 있다.

## 완료·제출

| 비교 | 기록 |
|---|---|
| 직접 호출 / RAG | 실제 모델 입력에 문서가 포함됐는가, 답변과 원문이 맞는가 |
| 문서에 없는 질문 | 알 수 없음을 밝혔는가, 근거 없는 값을 만들었는가 |
| top-k 1 / 3 | 실제 반환 수·근거·입력 토큰·답변 차이 |
| 문서 업데이트, 수행한 경우 | 변경 전후 검색 원문과 답변, Sync 상태 |

이유를 원문과 API 요청에 근거해 설명하면 된다. 품질이 개선되지 않거나 차이가 없는 관찰도 그대로 제출한다.

다음: [정리](04-cleanup.md), [보고서](templates/report.md)
