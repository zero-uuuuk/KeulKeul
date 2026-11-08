# Assignment1: 따릉이 실시간 데이터를 Firehose로 S3에 쌓기

서울 따릉이 실시간 API를 30초마다 호출하는 폴러를 **Lambda + EventBridge**로 AWS 안에 띄우고, Amazon Data Firehose가 S3에 자동으로 파일을 쌓는 것을 확인한다. 노트북에는 아무것도 설치하지 않는다.

참고 자료:

- https://docs.aws.amazon.com/firehose/latest/dev/basic-create.html
- https://docs.aws.amazon.com/firehose/latest/dev/create-destination.html#create-destination-s3
- https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html

> ⚠️ **중요**
>
> Firehose·Lambda·EventBridge 모두 실습 규모에서는 수십 원 수준이다. 다만 폴러 스케줄을 켜 둔 채 잊으면 S3에 계속 쌓이고 서울 API 호출 한도도 소진되므로, 실습이 끝나면 EventBridge 스케줄을 반드시 **비활성화**한다.

## 0. 사전 준비

- 서울열린데이터광장 인증키 (https://data.seoul.go.kr → 나의 화면 → 인증키 관리)
- AWS 계정 (**유료 플랜**) 및 IAM 권한
    - S3
    - Amazon Data Firehose
    - AWS Lambda
    - Amazon EventBridge
    - IAM (역할 생성)
- 실습 리전: `ap-northeast-2`
    - 콘솔 오른쪽 위 **톱니바퀴(⚙) 아이콘** → 통합 설정 → **기본 리전(Default region)** → 편집 → `아시아 태평양(서울)`로 바꿔 둔다 (또는 주소창에 `https://console.aws.amazon.com/settings/home`). IAM처럼 리전이 없는 화면을 다녀오면 콘솔이 기본 리전(버지니아)으로 바뀌는 일이 잦다
- 제공된 샘플 폴더: 깃허브 `assignment/week16-firehose`
    - `lambda_poller.py` — 이번 과제. Lambda 콘솔에 붙여넣는다
    - `lambda_transform.py` — Assignment2
    - `lambda_aggregator.py`, `web/index.html` — Assignment3

> ⚠️ **중요 — 계정 플랜**
>
> Amazon Data Firehose는 AWS 무료 플랜(Free plan)에서 쓸 수 없다. Firehose 콘솔에 들어갔을 때 "Complete your account setup" 화면이 뜨면 무료 플랜 상태다. 계정 메뉴 → **AWS Settings** → **Upgrade plan**으로 유료 플랜(종량제)으로 올린 뒤 진행한다. 업그레이드 자체는 무료이고 실습 비용은 수십 원 수준이다. 반영까지 몇 분 걸릴 수 있다.

> ⚠️ **중요 — API 호출 한도**
>
> 서울열린데이터광장 인증키는 하루 호출 한도(기본 1,000회)가 있다. 폴러는 30초마다 3회 호출하므로 하루 종일 켜 두면 8,640회로 한도를 넘긴다. 실습·발표 중에만 1분 스케줄로 켜고, 평소에는 비활성화하거나 5분 스케줄로 둔다.

## 1. 전체 구조 이해

```
Amazon EventBridge Scheduler  ─ 1분마다 ─▶  AWS Lambda (week18-firehose-poller)
                                                 │  API 호출 → 30초 대기 → API 호출  (= 30초 폴링)
                                                 │  레코드 약 2,700건 × 2 → put_record_batch
                                                 ▼
                                   Amazon Data Firehose (week18-firehose-stream)
                                                 │  버퍼: 1 MiB 또는 60초 중 먼저 도달하면 flush
                                                 ▼
                                   Amazon S3 (keulkeul-week18-{ACCOUNT_ID}-{성})
                                        raw/2026/11/09/04/week18-firehose-stream-...   ← 60초마다 파일 1개
```

| 구성 요소 | 역할 |
| --- | --- |
| EventBridge Scheduler | cron 역할. 1분마다 Lambda를 깨운다 |
| Lambda 폴러 | API를 호출해 레코드를 Firehose로 보내는 데이터 생산자. 한 번 실행에 30초 간격으로 2회 호출 |
| Firehose 스트림 | 레코드를 받아 버퍼에 모았다가 S3에 저장 |
| S3 버킷 | 최종 저장소. 파일은 JSON 줄 단위(JSON Lines) |
| IAM Role (2개) | Firehose가 S3에 쓸 권한 / Lambda가 Firehose에 넣을 권한 |

> 💡 **참고 — 로컬 vs 클라우드**
>
> 폴러를 노트북에서 돌리면 노트북을 끄는 순간 데이터가 멈춘다. Lambda + EventBridge로 올리면 AWS가 대신 실행하므로 노트북 없이도 계속 쌓인다. EventBridge는 리눅스 cron과 같은 스케줄러이고, 최소 주기가 1분이라 Lambda 안에서 30초 간격으로 2번 호출해 30초 폴링을 만든다.

## 체크리스트

위에서 아래로 순서대로 한다. 각 줄을 끝내고 ✅ 기준을 확인한 뒤 다음으로 넘어간다.

| 순서 | 단계 | 만드는 것 | 놓치기 쉬운 것 |
| --- | --- | --- | --- |
| 2 | 인증키 확인 | — | 브라우저에서 `INFO-000` 확인 |
| 3 | S3 버킷 | `keulkeul-week18-{ACCOUNT_ID}-{성}` | 리전 서울 |
| 4 | Firehose 스트림 | `week18-firehose-stream` | New line delimiter 켜기, Dynamic partitioning은 끈 채로 |
| 5-1~5-3 | Lambda 폴러 | `week18-firehose-poller` + 환경 변수 2개 + Timeout 1분 30초 | 환경 변수 **2개 모두** |
| **5-4** | **Lambda 역할 권한** | `AmazonKinesisFirehoseFullAccess` | **이걸 빼면 `AccessDenied`** |
| 5-5 | Lambda Test | `sent=2736` | |
| 6 | EventBridge 스케줄 | `week18-firehose-poller-1min` | 대상 함수 이름 |
| 7 | S3 확인 | `raw/` 폴더 | 3~5분 대기 |

## 2. 인증키 확인

브라우저 주소창에 아래 주소를 넣어 API가 응답하는지 확인한다. `{인증키}` 자리에 발급받은 키를 넣는다.

```
http://openapi.seoul.go.kr:8088/{인증키}/json/bikeList/1/5/
```

정상 응답:

```
{"rentBikeStatus":{"list_total_count":5,"RESULT":{"CODE":"INFO-000","MESSAGE":"정상 처리되었습니다."},"row":[{"rackTotCnt":"15","stationName":"102. 망원역 1번출구 앞", ...
```

✅ `CODE":"INFO-000"`이 보이면 성공. 이 키를 5번에서 Lambda 환경 변수로 넣는다.

> ⚠️ **오류**
>
> - `INFO-100` 또는 `INFO-200` → 인증키 오류. 키를 복사할 때 앞뒤 공백이 들어갔는지 확인한다.
> - `ERROR-336` 또는 호출 한도 메시지 → 하루 호출 한도 초과. 다음 날 다시 하거나 트래픽 증가를 신청한다.

## 3. S3 버킷 생성

1. AWS Console 오른쪽 위 리전이 `ap-northeast-2`(서울)인지 확인한다.
2. 검색창에 **S3**를 입력하고 **S3**로 이동한다.
3. 왼쪽 메뉴 **General purpose buckets(범용 버킷)** → **Create bucket(버킷 만들기)**을 클릭한다.
4. 아래 항목만 설정하고 나머지는 기본값을 둔다.

**General configuration(일반 구성)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Bucket type(버킷 유형) | `General purpose(범용)` | 기본 선택. Directory·Table 버킷이 아닌지만 확인 |
| Bucket name(버킷 이름) | `keulkeul-week18-{ACCOUNT_ID}-{성}` | 전 세계에서 유일해야 해서 계정 ID와 성을 넣는다. 소문자·숫자·하이픈만. 계정 ID는 콘솔 오른쪽 위 계정 메뉴에서 확인 |

**Block Public Access settings(퍼블릭 액세스 차단 설정)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Block all public access(모든 퍼블릭 액세스 차단) | ✔ 체크 유지 (기본값) | Firehose는 IAM Role로 쓰기 때문에 공개가 필요 없다. 풀지 않는다 |

5. **Create bucket(버킷 만들기)**을 클릭한다.

✅ **General purpose buckets** 목록에 `keulkeul-week18-{ACCOUNT_ID}-{성}`이 보이면 성공

> 💡 **참고**
>
> Object Ownership, Versioning, Tags, Encryption(SSE-S3), Object Lock은 전부 기본값 그대로 둔다. 화면에 Namespace(네임스페이스)나 Table name이 보인다면 **Table buckets** 화면에 들어간 것이니 **General purpose buckets**로 돌아간다.

> ⚠️ **오류**
>
> - `Bucket with the same name already exists` → 이름이 다른 사람과 겹친 것. 이름 뒤에 숫자를 붙인다 (`keulkeul-week18-{ACCOUNT_ID}-{성}-01`).
> - `Bucket name should not contain uppercase characters` → 대문자·공백·밑줄은 안 된다. 소문자와 하이픈만 쓴다.

### 3-1. S3 버킷에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Bucket name | `keulkeul-week18-{ACCOUNT_ID}-{성}` | Firehose가 파일을 저장할 위치 |
| Region | `ap-northeast-2` | Firehose 스트림과 같은 리전 |
| Block public access | 켜짐 | 외부 공개 차단 |

## 4. Firehose 스트림 생성

1. 검색창에 **Firehose**를 입력하고 **Amazon Data Firehose**로 이동한다.
2. **Create Firehose stream(Firehose 스트림 생성)**을 클릭한다.
3. 아래 항목만 설정하고 나머지는 기본값을 둔다. 접힌 섹션은 펼친다.

**Choose source and destination(소스 및 대상 선택)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Source(소스) | `Direct PUT` | 폴러가 SDK로 직접 레코드를 넣는다 |
| Destination(대상) | `Amazon S3` | 저장 위치 |

**Firehose stream name(Firehose 스트림 이름)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Firehose stream name | `week18-firehose-stream` | 폴러의 `--stream` 값과 같아야 한다. 생성 후 변경 불가 |

**Destination settings(대상 설정)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| S3 bucket(S3 버킷) | **Browse(찾아보기)** → `keulkeul-week18-{ACCOUNT_ID}-{성}` | 3번에서 만든 버킷 |
| New line delimiter(새 줄 구분 기호) | `Enabled(활성화됨)` | 한 줄 = 한 레코드로 저장. 끄면 JSON이 한 줄에 붙어 Athena가 못 읽는다 |
| S3 bucket prefix(S3 버킷 접두사) | `raw/` | 파일이 저장될 폴더. 뒤에 `YYYY/MM/dd/HH/`가 자동으로 붙는다 |
| S3 bucket error output prefix(오류 출력 접두사) | `error/` | 전송 실패 레코드가 저장될 폴더 |

**Buffer hints, compression, file extension and encryption(버퍼 힌트, 압축, 파일 확장자 및 암호화)** — 펼친다

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Buffer size(버퍼 크기) | `1` MiB | 모인 데이터가 이 크기에 도달하면 S3에 파일 생성 (기본값 5) |
| Buffer interval(버퍼 간격) | `60` seconds | 크기가 안 차도 이 시간이 지나면 파일 생성 (기본값 300). 둘 중 먼저 도달하는 쪽이 적용된다 |

**Advanced settings(고급 설정)** — 펼친다

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Service access(서비스 액세스) | `Create or update IAM role(IAM 역할 생성 또는 업데이트)` (기본값) | Firehose가 S3에 쓸 권한. 자동 생성되는 역할 이름은 그대로 둔다 |

4. **Create Firehose stream(Firehose 스트림 생성)**을 클릭한다.

✅ 스트림 목록에 `week18-firehose-stream`이 보이고 Status가 `Active(활성)`이면 성공 (1~2분 걸릴 수 있다)

> 💡 **참고**
>
> Transform and convert records(Lambda 변환, 형식 변환)와 Dynamic partitioning은 Assignment1에서는 끈 상태로 둔다. Assignment2에서 켠다. Compression, File extension, Encryption, Error logging, Tags도 기본값 그대로.

> ⚠️ **오류**
>
> - Destination에서 버킷이 목록에 안 보인다면 → 버킷 리전이 `ap-northeast-2`가 아닌 것. 콘솔 오른쪽 위 리전을 확인하고 버킷을 서울 리전에 다시 만든다.
> - `Status: Creating`이 5분 넘게 유지된다면 → 페이지를 새로고침한다. 그래도 그대로면 스트림을 삭제하고 다시 만든다.
> - `Firehose is unable to assume role arn:aws:iam::...:role/service-role/KinesisFirehoseServiceRole-...` → 콘솔이 방금 만든 IAM 역할이 아직 전파되지 않은 것. 역할 자체는 생성되어 있으므로, 같은 생성 화면에서 Service access를 **`Choose existing IAM role(기존 IAM 역할 선택)`**으로 바꾸고 드롭다운에서 방금 생긴 `KinesisFirehoseServiceRole-week18-f-ap-northeast-2-...`를 고른 뒤 다시 **Create**한다.
> - 위 에러의 역할 이름에 `us-east-1`이 들어 있다면 → 리전이 버지니아로 바뀐 것. 콘솔 오른쪽 위 리전을 `ap-northeast-2`로 바꾸고 처음부터 다시 만든다. 버지니아에 생긴 역할은 IAM → Roles에서 나중에 삭제한다.
> - 생성 중 `not authorized to perform: iam:CreateRole` → 계정에 IAM 역할 생성 권한이 없는 것. 관리자 계정으로 역할을 먼저 만들어 달라고 요청한다.

### 4-1. Firehose 스트림에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Source | `Direct PUT` | 폴러가 SDK로 직접 레코드를 넣음 |
| Destination | `Amazon S3` | 최종 저장 위치 |
| S3 bucket prefix | `raw/` | 원본 그대로 저장되는 폴더 |
| Buffer size / interval | `1 MiB` / `60 s` | 둘 중 먼저 도달하면 S3에 파일 생성 |
| New line delimiter | `Enabled` | 레코드를 줄 단위로 저장 |
| Service access role | 자동 생성 | Firehose가 S3에 쓰는 권한 |

## 5. Lambda 폴러 생성

### 5-1. 함수 생성

1. 검색창에 **Lambda**를 입력하고 **Lambda**로 이동한다. 리전이 `ap-northeast-2`인지 확인한다.
2. **Create function(함수 생성)**을 클릭한다.

**Basic information(기본 정보)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| 생성 방식 | `Author from scratch(새로 작성)` | |
| Function name(함수 이름) | `week18-firehose-poller` | |
| Runtime(런타임) | `Python 3.12` | |

3. **Create function(함수 생성)**을 클릭한다.

### 5-2. 코드 붙여넣기

1. **Code(코드)** 탭의 에디터에서 `lambda_function.py` 내용을 전부 지운다.
2. 깃허브 `assignment/week16-firehose` 폴더의 `lambda_poller.py`를 열어 전체 복사 → 붙여넣는다.
3. **Deploy(배포)**를 클릭한다.

✅ "Successfully updated the function" 메시지가 뜨면 성공

### 5-3. 환경 변수와 제한 시간

1. **Configuration(구성)** 탭 → 왼쪽 **Environment variables(환경 변수)** → **Edit(편집)** → **Add environment variable(환경 변수 추가)**

| Key | Value | 의미 |
| --- | --- | --- |
| `SEOUL_API_KEY` | 2번에서 확인한 인증키 | API 호출에 사용 |
| `FIREHOSE_STREAM` | `week18-firehose-stream` | 레코드를 보낼 스트림. 4번의 이름과 같아야 한다 |

2. **Save(저장)**
3. 왼쪽 **General configuration(일반 구성)** → **Edit(편집)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Timeout(제한 시간) | `1` min `30` sec | 2회 호출 + 30초 대기 + 전송 시간. 기본 3초면 바로 끊긴다 |

4. **Save(저장)**

### 5-4. Firehose 쓰기 권한

Lambda가 Firehose에 레코드를 넣으려면 권한이 필요하다.

1. **Configuration(구성)** 탭 → 왼쪽 **Permissions(권한)** → Execution role의 역할 이름(`week18-firehose-poller-role-...`) 클릭 → IAM 콘솔이 열린다
2. **Permissions(권한)** 탭 → **Add permissions(권한 추가)** ▼ → **Attach policies(정책 연결)**
3. 검색창에 `AmazonKinesisFirehoseFullAccess` 입력 → 체크 → **Add permissions(권한 추가)**

✅ 역할의 정책 목록에 `AWSLambdaBasicExecutionRole`과 `AmazonKinesisFirehoseFullAccess` 2개가 보이면 성공

### 5-5. 테스트 실행

1. Lambda 함수 화면 → **Test(테스트)** 탭 → Event name(이벤트 이름): `manual` → **Save(저장)** → **Test(테스트)**
2. 약 35초 뒤 실행 결과가 뜬다.

정상 응답 (Execution results):

```
[{"polled_at": "2026-11-09T13:46:28+09:00", "sent": 2736, "failed": 0}, {"polled_at": "2026-11-09T13:46:58+09:00", "sent": 2736, "failed": 0}]
```

✅ `sent`가 2,700 안팎이고 `failed`가 0이면 성공

> ⚠️ **오류**
>
> - `KeyError: 'SEOUL_API_KEY'` → 5-3의 환경 변수를 저장하지 않은 것.
> - `Task timed out after 3.00 seconds` → 5-3의 제한 시간을 늘리지 않은 것.
> - `AccessDeniedException ... firehose:PutRecordBatch` → 5-4의 권한을 붙이지 않은 것.
> - `ResourceNotFoundException: Firehose stream ... not found` → `FIREHOSE_STREAM` 값이 4번의 스트림 이름과 다르거나 리전이 다른 것.
> - `API 오류: INFO-100` → 인증키 값이 틀린 것. 2번으로 돌아가 확인한다.

### 5-6. Lambda 폴러에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Function name | `week18-firehose-poller` | EventBridge가 호출할 함수 |
| 환경 변수 | `SEOUL_API_KEY`, `FIREHOSE_STREAM` | 키와 목적지 |
| Timeout | `1 min 30 sec` | 2회 호출 여유 |
| 실행 역할 정책 | `AmazonKinesisFirehoseFullAccess` | Firehose에 넣을 권한 |

## 6. EventBridge 스케줄 생성

Lambda를 1분마다 자동으로 호출하는 스케줄을 만든다. 아래 항목만 설정하고 **나머지는 전부 기본값으로 둔다.**

1. 검색창에 **EventBridge**를 입력하고 **Amazon EventBridge**로 이동한다.
2. 왼쪽 메뉴 **Scheduler** → **Schedules(일정)** → **Create schedule(일정 생성)**

**Step 1 — Specify schedule detail(일정 세부 정보 지정)**

| 옵션 | 입력값 |
| --- | --- |
| Schedule name(일정 이름) | `week18-firehose-poller-1min` |
| Occurrence(발생) | `Recurring schedule(반복 일정)` |
| Schedule type(일정 유형) | `Rate-based schedule(속도 기반 일정)` |
| Rate expression(속도 표현식) | `1` `minutes` |
| Flexible time window(유연한 기간) | `Off(끄기)` |

→ **Next(다음)**

**Step 2 — Select target(대상 선택)**

| 옵션 | 입력값 |
| --- | --- |
| Templated targets(템플릿 기반 대상) | **AWS Lambda — Invoke** 타일 클릭 |
| Lambda function(Lambda 함수) | `week18-firehose-poller` |

→ **Next(다음)**

**Step 3 — Settings(설정)**

바꿀 것 없음. → **Next(다음)**

**Step 4 — Review(검토)**

→ **Create schedule(일정 생성)**

✅ Schedules 목록에 `week18-firehose-poller-1min`이 `Enabled(활성화됨)`로 보이면 성공

> ⚠️ **오류**
>
> - Step 2 드롭다운에 `week18-firehose-poller`가 없다면 → 콘솔 리전이 `ap-northeast-2`가 아니거나 5번의 함수 생성을 안 한 것.
> - Lambda → **Monitor(모니터링)** 탭에서 2~3분이 지나도 Invocations가 0이라면 → 스케줄 상태가 Enabled인지, 대상 함수가 맞는지 확인한다.
> - Invocations는 올라가는데 Errors도 같이 올라간다면 → **View CloudWatch logs**에서 에러 메시지를 보고 5-5의 오류 블록을 따른다.

## 7. 배포 확인

### 7-1. Firehose 모니터링

1. **Amazon Data Firehose** → `week18-firehose-stream` 클릭 → **Monitoring(모니터링)** 탭
2. 스케줄 생성 후 3~4분 기다린 뒤 다음 그래프를 확인한다.
    - **Incoming records(수신 레코드)**: 30초마다 약 2,700건
    - **Records delivered to Amazon S3(S3로 전송된 레코드)**: 60초마다 약 5,400건

✅ 두 그래프에 값이 찍히기 시작하면 성공 (그래프 반영까지 2~3분 지연이 있다)

### 7-2. S3 파일 확인

1. **S3** → `keulkeul-week18-{ACCOUNT_ID}-{성}` 클릭
2. `raw/` → `2026/` → `11/` → `04/` → `{시}/` 순서로 들어간다 (UTC 기준이라 한국 시간보다 9시간 전 폴더에 들어 있다)
3. `week18-firehose-stream-1-2026-11-04-05-02-11-...` 형식의 파일이 60초마다 하나씩 늘어난다.
4. 파일 하나를 클릭 → **Download(다운로드)** → 메모장으로 연다.

정상 응답 (파일 내용):

```
{"rackTotCnt": "15", "stationName": "102. 망원역 1번출구 앞", "parkingBikeTotCnt": "17", ..., "polled_at": "2026-11-04T14:02:11+09:00"}
{"rackTotCnt": "14", "stationName": "103. 망원역 2번출구 앞", "parkingBikeTotCnt": "6", ..., "polled_at": "2026-11-04T14:02:11+09:00"}
```

주요 필드:

| 필드 | 예시 | 의미 |
| --- | --- | --- |
| `stationName` | `"102. 망원역 1번출구 앞"` | 대여소 이름. 앞 숫자는 대여소 번호 |
| `rackTotCnt` | `"15"` | 거치대 개수 |
| `parkingBikeTotCnt` | `"17"` | 지금 세워져 있는 자전거 수 |

숫자가 전부 따옴표 붙은 **문자열**로 들어온다. 이대로는 Athena에서 합계를 구할 수 없어서 Assignment2에서 Lambda로 숫자 타입으로 바꾼다.

✅ 한 줄에 레코드 하나씩, 파일 하나에 약 5,400줄이면 성공

> ⚠️ **오류**
>
> - 5분이 지나도 `raw/` 폴더가 안 생긴다면 → 먼저 Lambda → Monitor에서 Invocations가 올라가는지 본다(스케줄 문제). 올라간다면 Firehose → `week18-firehose-stream` → **Destination error logs(대상 오류 로그)**를 본다. `S3 AccessDenied`가 있으면 4번의 Service access role이 버킷에 권한이 없는 것. 스트림 **Edit(편집)**에서 IAM role을 다시 `Create or update`로 저장한다.
> - 파일은 생기는데 내용이 한 줄에 전부 붙어 있다면 → New line delimiter가 꺼진 것. 스트림 Edit에서 `Enabled`로 바꾼다. 이미 저장된 파일은 그대로이고 새 파일부터 적용된다.
> - 폴더가 `raw/2026/11/04/` 다음에 비어 있다면 → UTC 시간 폴더를 잘못 본 것. 한국 시간 14시면 `05/` 폴더를 연다.
