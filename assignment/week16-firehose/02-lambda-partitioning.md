# Assignment2: Lambda 변환과 Dynamic Partitioning으로 데이터 가공하기

Firehose 스트림에 Lambda 함수를 붙여 레코드를 가공하고, 가공된 값으로 S3 폴더를 자동으로 나눈다. 깨진 레코드는 별도 폴더로 분리되는 것을 확인한다.

참고 자료:

- https://docs.aws.amazon.com/firehose/latest/dev/data-transformation.html
- https://docs.aws.amazon.com/firehose/latest/dev/dynamic-partitioning.html

> ⚠️ **중요**
>
> Lambda 호출은 월 100만 회까지 무료이고 Firehose Dynamic Partitioning은 GB당 소액이 추가된다. 실습 규모에서는 수십 원 수준이다. 실습이 끝나면 EventBridge 스케줄을 반드시 비활성화한다.

## 0. 사전 준비

- Assignment1 완료 (S3 버킷, Firehose 스트림, Lambda 폴러 `week18-firehose-poller`, EventBridge 스케줄)
    - Lambda 콘솔에 `week18-firehose-poller`가 없다면 리전이 `ap-northeast-2`인지 먼저 확인하고, 그래도 없으면 Assignment1의 5번·6번을 먼저 한다
- 깃허브 `assignment/week16-firehose` 폴더의 `lambda_transform.py`
- AWS 계정 및 IAM 권한
    - AWS Lambda
    - Amazon Data Firehose
    - IAM
- 실습 리전: `ap-northeast-2`

## 1. 전체 구조 이해

```
EventBridge (1분) → Lambda 폴러 (CORRUPT_PER_RUN=5)
  ↓  정상 레코드 2,731건 + 일부러 깨뜨린 레코드 5건
Firehose (week18-firehose-stream-v2)
  ↓  버퍼 → Lambda 호출
Lambda (week18-firehose-transform)
  ├─ 정상: 문자열 → 숫자 변환, 파생 필드 추가, hour 값을 파티션 키로 반환
  └─ 깨짐: ProcessingFailed 반환
  ↓
S3
  ├─ clean/hour=16/   ← 변환된 레코드 (hour 값마다 폴더가 생김)
  └─ error/processing-failed/   ← 깨진 레코드 원본 그대로
```

Assignment1과의 차이:

| 구분 | Assignment1 | Assignment2 |
| --- | --- | --- |
| 스트림 | `week18-firehose-stream` | `week18-firehose-stream-v2` (새로 생성) |
| 레코드 내용 | API 원본 그대로 (숫자가 문자열) | 숫자 변환 + 파생 필드 5개 추가 |
| S3 폴더 | `raw/YYYY/MM/dd/HH/` (Firehose 기본) | `clean/hour=HH/` (레코드 값으로 분기) |
| 깨진 레코드 | 그대로 저장됨 | `error/` 폴더로 분리 |

> 💡 **참고**
>
> Dynamic Partitioning은 스트림을 만들 때만 켤 수 있고 나중에 추가할 수 없다. 그래서 Assignment1 스트림을 수정하지 않고 새 스트림을 만든다.

### 1-1. Lambda가 추가하는 필드

| 필드 | 예시 | 의미 |
| --- | --- | --- |
| `station_no` | `204` | `stationName` 앞 번호를 숫자로 추출 |
| `empty_racks` | `8` | 빈 거치대 수 = `rackTotCnt - parkingBikeTotCnt` (음수면 0) |
| `is_empty` | `false` | 자전거가 0대인지 |
| `is_overflow` | `false` | 자전거가 거치대 수보다 많은지 |
| `hour` | `"16"` | `polled_at`의 시(KST). Dynamic Partitioning 키 |

기존 숫자 필드(`rackTotCnt`, `parkingBikeTotCnt`, `shared`, 위도·경도)는 문자열에서 숫자 타입으로 바뀐다.

## 체크리스트

| 순서 | 단계 | 만드는 것 | 놓치기 쉬운 것 |
| --- | --- | --- | --- |
| 2 | 변환 Lambda | `week18-firehose-transform` + Timeout 1분 | 환경 변수·추가 권한 **없음** (S3 접근은 Firehose가 함) |
| **3** | **Firehose 역할 권한** | `AWSLambdaRole` | **이걸 빼면 전부 `error/`로 감** |
| 4 | Firehose 스트림 v2 | `week18-firehose-stream-v2` | Dynamic partitioning **Enabled**, 버퍼 64 MiB, Service access는 기존 역할 선택 |
| 5 | 폴러 환경 변수 | `FIREHOSE_STREAM` → v2, `CORRUPT_PER_RUN` 추가 | **`SEOUL_API_KEY`는 지우지 않는다** (3개여야 함) |
| 6 | 확인 | `clean/hour=HH/`, `error/processing-failed/` | 첫 파일까지 5분 |

## 2. Lambda 함수 생성

1. 검색창에 **Lambda**를 입력하고 **Lambda**로 이동한다.
2. **Create function(함수 생성)**을 클릭한다.
3. 아래 항목만 설정하고 나머지는 기본값을 둔다.

**Create function(함수 생성)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| 생성 방식 | `Author from scratch(새로 작성)` | 템플릿 없이 직접 코드 입력 |

**Basic information(기본 정보)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Function name(함수 이름) | `week18-firehose-transform` | Firehose 설정에서 이 이름으로 고른다 |
| Runtime(런타임) | `Python 3.12` | 코드가 Python 3.12 기준으로 작성됨 |
| Architecture(아키텍처) | `x86_64` (기본값) | |

**Change default execution role(기본 실행 역할 변경)** — 펼친다

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Execution role(실행 역할) | `Create a new role with basic Lambda permissions(기본 Lambda 권한을 가진 새 역할 생성)` (기본값) | CloudWatch Logs에 로그를 쓸 권한만 있으면 된다. S3 접근은 Lambda가 아니라 Firehose가 하므로 추가 권한 불필요 |

4. **Create function(함수 생성)**을 클릭한다.

✅ 함수 페이지가 열리고 상단에 `week18-firehose-transform`이 보이면 성공

### 2-1. 코드 붙여넣기

1. 함수 페이지 아래 **Code(코드)** 탭의 코드 에디터에서 `lambda_function.py` 내용을 전부 지운다.
2. 깃허브 `assignment/week16-firehose` 폴더의 `lambda_transform.py`를 메모장으로 열어 전체 복사 → 에디터에 붙여넣는다.
3. **Deploy(배포)**를 클릭한다.

✅ 에디터 위에 "Successfully updated the function" 메시지가 뜨면 성공

> ⚠️ **오류**
>
> - Deploy 버튼이 회색이라면 → 코드가 바뀌지 않은 것. 붙여넣기가 됐는지 확인한다.
> - 붙여넣은 코드에 들여쓰기가 깨져 있다면 → 메모장 대신 VS Code나 브라우저에서 파일을 열어 복사한다. 깃허브 페이지에서 **Raw** 버튼을 눌러 복사하면 깨지지 않는다.

### 2-2. 타임아웃 늘리기

Firehose는 레코드를 수천 건씩 묶어 Lambda를 호출하므로 기본 3초로는 부족하다.

1. **Configuration(구성)** 탭 → 왼쪽 **General configuration(일반 구성)** → **Edit(편집)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Timeout(제한 시간) | `1` min `0` sec | 레코드 5,000건 변환에 수 초 걸림. 1분이면 충분 |
| Memory(메모리) | `128` MB (기본값) | 변환 로직이 가벼워 기본값으로 충분 |

2. **Save(저장)**을 클릭한다.

✅ General configuration에 Timeout `1 min 0 sec`이 보이면 성공

### 2-3. 테스트 (선택)

실제 Firehose를 연결하기 전에 콘솔에서 한 번 실행해 볼 수 있다.

1. **Test(테스트)** 탭 → Event name(이벤트 이름): `firehose-sample`
2. Template(템플릿) 드롭다운에서 `kinesis-firehose` 검색 → **Kinesis Firehose** 선택
3. **Save(저장)** → **Test(테스트)**

✅ 실행 결과에 `"result": "Ok"` 또는 `"result": "ProcessingFailed"`가 보이면 성공 (샘플 데이터가 따릉이 형식이 아니라 ProcessingFailed가 정상)

### 2-4. Lambda에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Function name | `week18-firehose-transform` | Firehose가 호출할 함수 |
| Runtime | `Python 3.12` | 코드 실행 환경 |
| Handler | `lambda_function.lambda_handler` (기본값) | 파일명.함수명. 코드의 `lambda_handler`와 일치 |
| Timeout | `1 min` | Firehose 배치 처리 시간 확보 |

## 3. Firehose 역할에 Lambda 호출 권한 추가

Assignment1에서 자동 생성된 Firehose 역할에는 S3 권한만 있고 Lambda를 호출할 권한이 없다. 스트림을 만들기 전에 먼저 붙인다.

1. 검색창에 **IAM**을 입력하고 **IAM**으로 이동한다.
2. 왼쪽 메뉴 **Roles(역할)** → 검색창에 `KinesisFirehoseServiceRole-week18` 입력 → `...-ap-northeast-2-...`로 끝나는 역할 클릭 (`us-east-1`이 들어간 것은 아님)
3. **Permissions(권한)** 탭 → **Add permissions(권한 추가)** ▼ → **Attach policies(정책 연결)**
4. 검색창에 `AWSLambdaRole` 입력 → 체크 → **Add permissions(권한 추가)**

✅ Permissions 탭 정책 목록에 `AWSLambdaRole`이 추가되면 성공

> 💡 **참고**
>
> 이 단계를 건너뛰면 스트림은 정상적으로 만들어지지만, 모든 레코드가 `error/processing-failed/`로 가고 `clean/`은 생기지 않는다. 파일을 열면 `"errorCode":"Lambda.InvokeAccessDenied"`가 보인다. 그때 이 단계를 하면 스트림을 다시 만들지 않아도 다음 버퍼부터 정상 동작한다.

## 4. Firehose 스트림 생성 (v2)

1. 검색창에 **Firehose**를 입력하고 **Amazon Data Firehose**로 이동한다. 리전이 `ap-northeast-2`인지 확인한다.
2. **Create Firehose stream(Firehose 스트림 생성)**을 클릭한다.
3. 아래 항목만 설정하고 나머지는 기본값을 둔다.

**Choose source and destination(소스 및 대상 선택)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Source(소스) | `Direct PUT` | Assignment1과 동일 |
| Destination(대상) | `Amazon S3` | Assignment1과 동일 |

**Firehose stream name(Firehose 스트림 이름)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Firehose stream name | `week18-firehose-stream-v2` | Assignment1 스트림과 구분 |

**Transform and convert records(레코드 변환 및 전환)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Transform source records with AWS Lambda(Lambda로 소스 레코드 변환) | ✔ **Turn on data transformation(데이터 변환 켜기)** 체크 | 레코드가 S3에 가기 전에 Lambda를 거친다 |
| AWS Lambda function(Lambda 함수) | **Browse(찾아보기)** → `week18-firehose-transform` | 2번에서 만든 함수 |
| Version or alias(버전 또는 별칭) | `$LATEST` (기본값) | 항상 최신 코드 사용 |
| Buffer size(버퍼 크기) | `1` MiB | Lambda를 호출하는 단위. 이 크기만큼 모이면 한 번 호출 |
| Buffer interval(버퍼 간격) | `60` seconds | 크기가 안 차도 60초마다 호출 |
| Convert record format(레코드 형식 변환) | 체크 해제 | Assignment3에서 켠다 |

**Destination settings(대상 설정)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| S3 bucket(S3 버킷) | **Browse** → `keulkeul-week18-{ACCOUNT_ID}-{성}` | Assignment1과 같은 버킷 |
| New line delimiter(새 줄 구분 기호) | `Enabled(활성화됨)` | Assignment1과 동일 |
| Dynamic partitioning(동적 파티셔닝) | `Enabled(활성화됨)` | 레코드 값으로 S3 폴더를 나눈다. **생성 후 변경 불가** |
| Multi record deaggregation(다중 레코드 분해) | `Not enabled(비활성화됨)` (기본값) | 한 레코드에 JSON 여러 개를 묶어 보낼 때만 사용. 폴러는 1건씩 보냄 |
| Inline parsing for JSON(JSON 인라인 구문 분석) | `Not enabled(비활성화됨)` (기본값) | Firehose가 직접 JSON을 파싱해 키를 뽑는 방식. 우리는 Lambda가 `metadata.partitionKeys.hour`로 키를 돌려주므로 끈다. 끈 상태에서는 키를 등록하는 칸이 나타나지 않는 것이 정상이다 — 키 이름은 아래 prefix 안에만 적는다 |
| S3 bucket prefix(S3 버킷 접두사) | `clean/hour=!{partitionKeyFromLambda:hour}/` | `!{partitionKeyFromLambda:hour}` 자리에 Lambda가 준 값이 들어가 `clean/hour=16/` 같은 폴더가 된다 |
| S3 bucket error output prefix(오류 출력 접두사) | `error/!{firehose:error-output-type}/` | 실패 유형별 폴더. Lambda가 ProcessingFailed를 돌려주면 `error/processing-failed/` |
| Retry duration(재시도 기간) | `300` seconds (기본값) | 파티셔닝 실패 시 재시도 시간 |

**Buffer hints, compression, file extension and encryption** — 펼친다

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Buffer size(버퍼 크기) | `64` MiB (기본값, Dynamic Partitioning 켜면 최소 64) | 파티션별로 따로 버퍼가 생기므로 최소값이 커진다 |
| Buffer interval(버퍼 간격) | `60` seconds | 60초마다 파티션 폴더마다 파일 1개 |

**Advanced settings(고급 설정)** — 펼친다

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Service access(서비스 액세스) | `Choose existing IAM role(기존 IAM 역할 선택)` → Assignment1에서 생긴 `KinesisFirehoseServiceRole-week18-f-ap-northeast-2-...` | 3번에서 Lambda 권한을 붙인 역할. 새로 만들면 Assignment1의 assume role 오류가 다시 날 수 있다 |

4. **Create Firehose stream(Firehose 스트림 생성)**을 클릭한다.

✅ 스트림 목록에 `week18-firehose-stream-v2`가 `Active(활성)`이고, 스트림을 클릭해 **Configuration(구성)** 탭 → Destination settings에서 **Dynamic partitioning: Enabled**로 보이면 성공. `Not enabled`로 보이면 삭제 후 다시 만든다

> ⚠️ **오류**
>
> - 생성은 되는데 나중에 `clean/`이 안 생기고 `error/processing-failed/` 파일에 `Lambda.InvokeAccessDenied`가 보인다면 → 3번을 건너뛴 것. 3번을 지금 해도 된다. 스트림 재생성 불필요.
> - `Firehose is unable to assume role` → Assignment1과 같은 전파 지연. 1분 기다렸다가 같은 화면에서 다시 Create.
> - S3 bucket prefix 입력 시 `Invalid prefix` → `!{partitionKeyFromLambda:hour}` 철자를 확인한다. 중괄호 안 공백, 대소문자 모두 정확해야 한다.
> - S3 bucket prefix 입력란 위에 Multi record deaggregation, Inline parsing 항목이 안 보인다면 → Dynamic partitioning을 `Enabled`로 바꾸지 않은 것. 바꾸면 아래에 나타난다.
> - 스트림을 만든 뒤 Dynamic partitioning을 켜려고 **Edit(편집)**해도 적용되지 않는다 → 생성 시에만 설정 가능. 스트림을 **Delete(삭제)**하고 다시 만든다.

### 4-1. Firehose 스트림 v2에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Data transformation | `week18-firehose-transform` | 레코드마다 Lambda 실행 |
| Dynamic partitioning | `Enabled`, key `hour` | Lambda 반환값으로 폴더 분기 |
| S3 bucket prefix | `clean/hour=!{partitionKeyFromLambda:hour}/` | 변환 결과 저장 위치 |
| Error output prefix | `error/!{firehose:error-output-type}/` | 실패 레코드 저장 위치 |
| Service access role | Assignment1 역할 재사용 | S3 쓰기 + Lambda 호출 권한 |

## 5. 폴러를 v2 스트림으로 돌리기 (손상 레코드 포함)

Assignment1의 Lambda 폴러는 그대로 두고 **환경 변수만 바꾼다**. 코드 수정이나 재배포는 없다.

1. **Lambda** → `week18-firehose-poller` → **Configuration(구성)** 탭 → **Environment variables(환경 변수)** → **Edit(편집)**

| Key | Value | 의미 |
| --- | --- | --- |
| `SEOUL_API_KEY` | (그대로 둔다) | Assignment1에서 넣은 값. 지우지 않는다 |
| `FIREHOSE_STREAM` | `week18-firehose-stream-v2` | 기존 값을 v2로 바꾼다 |
| `CORRUPT_PER_RUN` | `5` | **새로 추가.** 매 폴링마다 레코드 5건을 일부러 깨뜨린다 (숫자 자리에 `N/A` 또는 `stationId` 누락) |

2. **Save(저장)**

EventBridge 스케줄이 Enabled 상태면 다음 분부터 바뀐 설정으로 실행된다. Disabled 상태면 EventBridge → Schedules → `week18-firehose-poller-1min` → **Enable**.

✅ 1~2분 뒤 Lambda → **Monitor** → **View CloudWatch logs** 최신 로그에 `sent=2736 failed=0`이 찍히면 성공. 깨진 5건도 Firehose는 일단 받아들인다. 분리는 변환 Lambda 단계에서 일어난다.

> ⚠️ **오류**
>
> - `ResourceNotFoundException` → `FIREHOSE_STREAM` 값 끝에 `-v2`가 빠졌는지 확인한다.
> - 로그에 `KeyError: 'SEOUL_API_KEY'` → 편집하면서 인증키 변수가 지워진 것. 다시 추가한다. 환경 변수는 세 개(`SEOUL_API_KEY`, `FIREHOSE_STREAM`, `CORRUPT_PER_RUN`)여야 한다.

## 6. 배포 확인

### 6-1. Lambda 실행 확인

1. **Lambda** → `week18-firehose-transform` → **Monitor(모니터링)** 탭
2. 1~2분 뒤 **Invocations(호출)** 그래프에 값이 찍힌다.
3. **View CloudWatch logs(CloudWatch 로그 보기)** → 최신 로그 스트림 클릭

정상 응답 (로그 안):

```
ProcessingFailed recordId=... reason=ValueError("invalid literal for int() with base 10: 'N/A'")
ProcessingFailed recordId=... reason=ValueError("missing fields: ['stationId']")
```

✅ 호출 그래프에 값이 있고, 로그에 `ProcessingFailed` 줄이 폴링마다 5개 안팎 보이면 성공

> ⚠️ **오류**
>
> - 2분이 지나도 Invocations가 0이라면 → Firehose가 Lambda를 못 부르는 것. Firehose → `week18-firehose-stream-v2` → **Destination error logs(대상 오류 로그)**에서 `Lambda.InvokeAccessDenied`가 있으면 3번(역할에 `AWSLambdaRole` 추가)을 한다.
> - 로그에 `Task timed out after 3.00 seconds` → 2-2의 타임아웃을 안 늘린 것. 1분으로 바꾼다.
> - 로그에 `Runtime.ImportModuleError: No module named 'lambda_function'` → 코드 파일 이름이 바뀐 것. Code 탭에서 파일명이 `lambda_function.py`인지 확인한다.

### 6-2. S3 폴더 확인

1. **S3** → `keulkeul-week18-{ACCOUNT_ID}-{성}`
2. 폴더가 Assignment1의 `raw/` 외에 두 개 더 생겼는지 본다.

```
raw/                      ← Assignment1
clean/
  └─ hour=16/             ← 변환된 레코드 (현재 시각 KST)
error/
  └─ processing-failed/   ← 깨진 레코드
       └─ 2026/11/06/07/  ← 이 아래는 UTC 기준 자동 폴더
```

3. `clean/hour=16/` 안의 파일 하나를 다운로드해 연다.

정상 응답:

```
{"stationId": "ST-50", "stationName": "204. 국회의사당역 5번출구 옆", "rackTotCnt": 13, "parkingBikeTotCnt": 5, "shared": 38, "stationLatitude": 37.52816391, "stationLongitude": 126.91702271, "polled_at": "2026-11-06T16:10:03+09:00", "station_no": 204, "empty_racks": 8, "is_empty": false, "is_overflow": false, "hour": "16"}
```

Assignment1 파일과 비교할 것:

| 항목 | `raw/` (Assignment1) | `clean/` (Assignment2) |
| --- | --- | --- |
| `rackTotCnt` | `"13"` (문자열) | `13` (숫자) |
| 파생 필드 | 없음 | `station_no`, `empty_racks`, `is_empty`, `is_overflow`, `hour` |
| 폴더 | 날짜/시간 자동 | `hour=` 값으로 분기 |

4. `error/processing-failed/` 안의 파일을 하나 열어 본다.

정상 응답:

```
{"attemptsMade":1,"arrivalTimestamp":...,"errorCode":"Lambda.ProcessingFailed","errorMessage":"...","rawData":"eyJyYWNrVG90Q250Ijog..."}
```

`rawData`는 원본 레코드를 base64로 감싼 것이다. 깨진 레코드가 버려지지 않고 보존되는 것을 확인한다.

✅ `clean/hour=HH/` 파일의 숫자에 따옴표가 없고 파생 필드 5개가 있으며, `error/processing-failed/`에 파일이 있으면 성공

> ⚠️ **오류**
>
> - `clean/` 대신 `clean/hour=/` (값이 빈 폴더)가 생긴다면 → Dynamic partitioning key 이름이 `hour`가 아니거나 Lambda 코드의 `partitionKeys` 키와 다른 것. 스트림은 수정 불가라 삭제 후 다시 만든다.
> - `clean/`은 생기는데 `error/`가 안 생긴다면 → `CORRUPT_PER_RUN`을 추가하지 않은 것. 정상 동작이다.
> - `error/processing-failed/` 파일이 수백 KB로 크고 폴링마다 생긴다면 → 깨진 5건이 아니라 전체가 실패하는 것. 파일을 열어 `errorCode`를 본다. `Lambda.InvokeAccessDenied`면 3번, `Task timed out`이면 2-2(타임아웃)를 확인한다.
> - 3분이 지나도 `clean/`이 안 생긴다면 → Dynamic Partitioning은 첫 파일이 나오기까지 5분 정도 걸릴 수 있다. 폴러를 켠 채 5분까지 기다린 뒤 S3를 **새로고침(↻)**한다.
> - 5분이 지나도 `error/`만 있고 `clean/`이 없다면 → 스트림의 Dynamic partitioning이 꺼진 채 만들어진 것. Configuration 탭에서 확인하고, `Not enabled`면 스트림을 삭제하고 3번부터 다시 만든다.
