# Assignment 1 · 모델 직접 호출과 응답 읽기

[← README](README.md) · [Assignment 2 →](assignment2.md)

**목표:** 모델 호출의 입력·생성 설정·응답을 구분합니다. 아직 Knowledge Base를 만들지 않은 상태에서 시작합니다.

## 1. 같은 질문에서 출력 상한만 바꾸기

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

## 2. 문서를 아직 제공하지 않은 질문

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
