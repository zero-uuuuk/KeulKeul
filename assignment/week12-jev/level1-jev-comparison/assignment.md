## Assignment: Lambda에서 OpenAI Terra와 Jev 판단 결과 비교하기

같은 고객 문의 문장을 **OpenAI GPT-5.6 Terra**(범용 LLM)와 **Jev**(TypeSafe AI의 결정 전용 모델)에 동시에 보내고, 분류 결과·지연시간·토큰 비용을 한 번에 비교하는 Lambda endpoint를 만든다.

| | Terra | Jev |
|---|---|---|
| 종류 | 범용 LLM (GPT-5.6 시리즈 중 균형형) | 결정 전용 모델 (Choice / Score / Noul) |
| Endpoint | `POST https://api.openai.com/v1/responses` | `POST https://api.typesafe.ai/v1/systemone` |
| 답변 방식 | Structured Outputs(JSON Schema)로 형식 강제 | 질문 유형별 타입 응답 + 선택지별 확률·confidence |
| 가격 (1M token) | input $2.00 / output $12.00 | input $0.042 / output $0 |

> [!NOTE]
> OpenAI에도 Jev와 같은 "결정 전용" 접근의 **Decisions API**가 있다. 미리 정해 둔 선택지 중에서 답을 고르게 하는 API로, 2026-09-29 DevDay에서 발표됐다. 다만 오늘(2026-10-05) 기준으로는 선택된 API 고객에게만 열린 limited preview 단계라 누구나 호출해볼 수는 없다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한 (Lambda, CloudWatch Logs)
- OpenAI API Key (`OPENAI_API_KEY`) — https://platform.openai.com/api-keys
- TypeSafe API Key (`TYPESAFE_API_KEY`) — https://console.typesafe.ai → API Keys
- 제공된 Lambda 코드: `lambda_function.py` (표준 라이브러리만 사용하므로 별도 패키징 없이 코드 붙여넣기로 배포 가능)

> [!IMPORTANT]
> API Key를 코드나 GitHub에 넣지 않는다. Lambda **환경 변수**로만 입력하고, 실습이 끝나면 Key를 폐기한다.

## 1. Lambda 함수 생성 (AWS 콘솔)

1. **Lambda** → **함수 생성** → **새로 작성**
2. 설정값:
    - 함수 이름: `keulkeul-week12-jev-comparison`
    - 런타임: `Python 3.14`
    - 아키텍처: `x86_64`
3. **코드** 탭의 `lambda_function.py`를 제공된 코드로 교체하고 **Deploy** 클릭

## 2. 환경 변수와 Timeout 설정

**구성** 탭 → **환경 변수** → **편집**

| Key | Value |
|---|---|
| `OPENAI_API_KEY` | 발급받은 OpenAI Key |
| `TYPESAFE_API_KEY` | 발급받은 TypeSafe Key |
| `OPENAI_MODEL` | `gpt-5.6-terra` (선택, 기본값과 동일) |
| `JEV_MODEL` | `jev-1.13.0` (선택, 버전 고정) |

**구성** 탭 → **일반 구성** → **편집** → Timeout을 `30초`로 변경한다. (기본 3초면 외부 API 호출 중 종료된다.)

## 3. Function URL 생성

1. **구성** 탭 → **함수 URL** → **함수 URL 생성**
2. Auth type: `NONE`, CORS: 끔
3. 생성된 URL을 복사한다.

> [!IMPORTANT]
> Auth type `NONE`이면 URL을 아는 누구나 호출해 내 API Key 비용이 발생한다. 실습이 끝나면 반드시 함수 URL과 Lambda를 삭제한다.

## 4. 호출해서 비교하기

`FUNCTION_URL`을 실제 URL로 교체해 실행한다.

```bash
curl -X POST "{FUNCTION_URL}" \
  -H "Content-Type: application/json" \
  -d '{"message": "My card was charged twice for one order and I need this fixed today."}'
```

응답에는 `terra`, `jev` 두 결과가 들어 있다.

- `answer`: 두 모델이 같은 형식으로 낸 `department`, `urgency`, `wants_refund`
- `latency_ms`: 각 API 호출에 걸린 시간
- `usage`, `cost_usd`: 사용 token과 계산된 비용
- `jev.confidence`: Jev만 제공하는 선택지 확률·confidence

아래 문장도 각각 호출해 결과를 비교한다.

```text
1. 택배가 일주일째 도착하지 않아요. 언제 오나요?
2. 앱이 로그인 화면에서 계속 튕겨요. 환불은 필요 없고 고쳐주세요.
3. 결제는 됐는데 주문 내역에 안 보여요. 급하진 않아요.
```

## 5. 리소스 정리

- Lambda 함수 URL 삭제 → Lambda 함수 삭제 → CloudWatch 로그 그룹 삭제
- OpenAI / TypeSafe API Key 폐기
