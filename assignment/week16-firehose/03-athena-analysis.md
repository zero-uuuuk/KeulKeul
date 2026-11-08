# Assignment3: Athena로 실시간 데이터 분석하기

Assignment2에서 S3 `clean/` 폴더에 쌓인 레코드를 Glue 테이블로 등록하고, Athena에서 SQL로 "지금 한양대역 앞 자전거 수"를 조회한다. 마지막으로 집계 Lambda가 1분마다 Athena 결과를 S3 정적 웹에 올려, 팀원 누구나 브라우저로 실시간 대시보드를 보게 한다.

참고 자료:

- https://docs.aws.amazon.com/athena/latest/ug/creating-tables.html
- https://docs.aws.amazon.com/athena/latest/ug/partitions.html

> ⚠️ **중요**
>
> Athena는 스캔한 데이터 1 TB당 $5 과금된다. 실습 데이터는 수백 MB라 쿼리 수십 번에 수십 원 수준이다. Glue 크롤러는 실행당 최소 10분 과금이므로 이 과제에서는 크롤러 대신 Athena DDL로 테이블을 만든다.

## 0. 사전 준비

- Assignment2 완료 (S3 `clean/hour=HH/` 폴더에 파일이 있어야 함)
- Lambda 폴러가 `week18-firehose-stream-v2`로 실행 중 (EventBridge 스케줄 Enabled, `CORRUPT_PER_RUN` 제거)
- AWS 계정 및 IAM 권한
    - Amazon Athena
    - AWS Glue (Data Catalog)
    - S3
    - AWS Lambda, Amazon EventBridge
- 제공 파일: `lambda_aggregator.py`, `web/index.html`, (대안용) `dashboard.py`
- 실습 리전: `ap-northeast-2`

## 1. 전체 구조 이해

```
S3  clean/hour=15/  clean/hour=16/  clean/hour=17/ ...
         ↑ 데이터는 그대로
Glue Data Catalog
  └─ week18_firehose_db.bike_status   ← "어느 S3 경로에 어떤 컬럼이 있다"는 목차
         ↑
Athena   SELECT ... WHERE hour = '16'   ← 목차를 보고 S3를 직접 읽어 SQL 실행
         ↑
EventBridge (1분) → Lambda 집계 (week18-firehose-aggregator)
         │   Athena 쿼리 3개 → data.json 생성
         ▼
S3 웹 버킷 (keulkeul-week18-{ACCOUNT_ID}-{성}-web)  ← 정적 웹 호스팅
   ├─ index.html   ← 팀원이 브라우저로 여는 대시보드
   └─ data.json    ← 1분마다 갱신
```

| 구성 요소 | 역할 |
| --- | --- |
| Glue Data Catalog | 테이블 이름 · 컬럼 · S3 경로 · 파티션 정보를 저장. 데이터 자체는 S3에 그대로 |
| Athena | 카탈로그를 보고 S3 파일을 직접 읽어 SQL 실행. 서버 없음 |
| 파티션 `hour` | `clean/hour=16/` 폴더 이름이 곧 파티션 값. `WHERE hour='16'`이면 그 폴더만 읽음 |
| Lambda 집계 | 1분마다 Athena를 조회해 대시보드용 `data.json` 하나로 가공. 새 시간 파티션도 자동 등록 |
| S3 정적 웹 | `index.html`과 `data.json`을 공개 URL로 제공. 서버 없이 팀원 모두가 접속 |

> 💡 **참고 — 로컬 vs 클라우드**
>
> 대시보드를 노트북에서 띄우면 본인만 본다. S3 정적 웹 호스팅에 올리면 URL 하나로 팀원 모두가 보고, 데이터 갱신도 Lambda가 대신 한다. 브라우저는 `data.json` 파일 하나만 30초마다 다시 읽는다.

## 체크리스트

| 순서 | 단계 | 만드는 것 | 놓치기 쉬운 것 |
| --- | --- | --- | --- |
| 2 | Athena 결과 위치 | `s3://.../athena-results/` | 끝에 `/` |
| 3 | DB·테이블·파티션 | `week18_firehose_db.bike_status` | `{ACCOUNT_ID}`, `{성}` 치환, `MSCK REPAIR TABLE` |
| 4 | 쿼리 5개 | — | |
| 5-1 | 웹 버킷 | `...-web` + 정적 호스팅 + 버킷 정책 | 퍼블릭 액세스 차단 **해제** |
| 5-2 | index.html 업로드 | — | 이 시점엔 `data.json 404`가 정상 |
| 5-3~5-4 | 집계 Lambda | `week18-firehose-aggregator` + 환경 변수 **5개** + Timeout 1분 | `WEB_BUCKET`에 `-web` |
| **5-5** | **Lambda 역할 권한** | `AmazonAthenaFullAccess`, `AmazonS3FullAccess` | **이걸 빼면 `AccessDenied`** |
| 5-6 | Lambda Test | `statusCode 200` → 대시보드 표시 | |
| 5-7 | EventBridge 스케줄 | `week18-firehose-aggregator-1min` | 시연 끝나면 Disable |
| (6) | 대안: 노트북 Streamlit | IAM 사용자 + `dashboard.py` | 5번 할 시간이 없을 때만. 발표 후 키 삭제 |

## 2. Athena 쿼리 결과 위치 설정

Athena는 쿼리 결과를 S3에 저장해야 실행된다. 처음 한 번만 설정한다.

1. 검색창에 **Athena**를 입력하고 **Athena**로 이동한다. 리전이 `ap-northeast-2`인지 확인한다.
2. **Launch query editor(쿼리 편집기 시작)**를 클릭한다.
3. 상단 **Settings(설정)** 탭 → **Manage(관리)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Location of query result(쿼리 결과 위치) | `s3://keulkeul-week18-{ACCOUNT_ID}-{성}/athena-results/` | 쿼리 결과 CSV가 저장될 폴더. 버킷 안에 새 폴더 이름을 적으면 자동 생성됨 |

4. **Save(저장)**을 클릭한다.

✅ Settings 탭에 Query result location이 표시되면 성공

> ⚠️ **오류**
>
> - 쿼리 실행 시 `No output location provided` → 이 설정을 안 한 것. 2번을 다시 한다.
> - 설정 화면이 없고 바로 에디터가 열린다면 → 이미 설정된 것. **Editor** 탭 오른쪽 위에 결과 위치가 보이는지 확인한다.

## 3. 데이터베이스와 테이블 생성

**Editor(편집기)** 탭의 쿼리 창에 아래 SQL을 하나씩 붙여넣고 **Run(실행)**한다.

### 3-1. 데이터베이스 생성

```sql
CREATE DATABASE IF NOT EXISTS week18_firehose_db;
```

✅ 왼쪽 **Database(데이터베이스)** 드롭다운에 `week18_firehose_db`가 생기면 성공. 드롭다운에서 선택해 둔다.

### 3-2. 테이블 생성

> ⚠️ **실행 전에** 맨 아래 `LOCATION` 줄의 `{ACCOUNT_ID}`와 `{성}`을 본인 버킷 이름으로 바꾼다. 예: `s3://keulkeul-week18-123456789012-kim/clean/`. 중괄호가 남아 있으면 `PatternSyntaxException: Illegal repetition` 에러가 난다.

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS week18_firehose_db.bike_status (
  stationId          string,
  stationName        string,
  rackTotCnt         int,
  parkingBikeTotCnt  int,
  shared             int,
  stationLatitude    double,
  stationLongitude   double,
  polled_at          string,
  station_no         int,
  empty_racks        int,
  is_empty           boolean,
  is_overflow        boolean
)
PARTITIONED BY (hour string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://keulkeul-week18-{ACCOUNT_ID}-{성}/clean/';
```

| 항목 | 의미 |
| --- | --- |
| `EXTERNAL TABLE` | 데이터는 S3에 두고 카탈로그에 정보만 등록. 테이블을 지워도 S3 파일은 남음 |
| `PARTITIONED BY (hour string)` | `clean/hour=16/` 폴더 이름을 `hour` 컬럼으로 인식. 컬럼 목록에는 `hour`를 넣지 않는다 |
| `JsonSerDe` | 한 줄에 JSON 하나인 파일을 읽는 방식. Assignment1에서 New line delimiter를 켠 이유 |
| `LOCATION` | `clean/`까지만. 그 아래 `hour=` 폴더는 파티션으로 자동 인식 |

✅ "Query successful"이 뜨고 왼쪽 **Tables(테이블)**에 `bike_status`가 보이면 성공

> ⚠️ **오류**
>
> - `FAILED: ParseException` 또는 `PatternSyntaxException: Illegal repetition near ... {ACCOUNT_ID}` → `LOCATION`의 `{ACCOUNT_ID}`나 `{성}`을 안 바꾼 것. 중괄호까지 지우고 실제 버킷 이름을 넣는다.
> - `Table already exists` → 이미 만든 것. 컬럼을 바꾸려면 `DROP TABLE week18_firehose_db.bike_status;` 후 다시 실행한다 (S3 데이터는 안 지워진다).

### 3-3. 파티션 등록

테이블을 만들어도 Athena는 아직 `hour=15/`, `hour=16/` 폴더가 있는지 모른다. S3를 훑어서 등록한다.

```sql
MSCK REPAIR TABLE week18_firehose_db.bike_status;
```

정상 응답:

```
Partitions not in metastore:  bike_status:hour=15  bike_status:hour=16
Repair: Added partition to metastore bike_status:hour=15
Repair: Added partition to metastore bike_status:hour=16
```

✅ `Added partition` 줄이 폴더 수만큼 나오면 성공

> 💡 **참고**
>
> 새 시간 폴더(`hour=17/`)가 생기면 이 명령을 다시 실행해야 Athena가 인식한다. 5번의 집계 Lambda를 만들면 그 뒤로는 Lambda가 매번 자동 등록하므로 손으로 할 필요가 없다.

> ⚠️ **오류**
>
> - 결과가 비어 있다면 → LOCATION 경로가 틀린 것. S3에서 `clean/` 폴더 경로를 복사해 3-2를 `DROP TABLE` 후 다시 만든다.
> - `Partitions not in metastore` 뒤에 아무것도 없고 `Repair` 줄도 없다면 → 이미 등록된 것. 정상이다.

### 3-4. 테이블에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Database | `week18_firehose_db` | 테이블을 묶는 논리 단위 |
| Table | `bike_status` | `clean/` 폴더를 가리키는 테이블 |
| Partition | `hour` | 시간대별 폴더. WHERE 조건으로 쓰면 스캔량이 줄어듦 |
| SerDe | JsonSerDe | JSON Lines 파일 해석 |

## 4. 쿼리 실행

아래 쿼리들을 하나씩 실행한다. 각 쿼리 결과 아래 **Data scanned(스캔한 데이터)**도 함께 본다.

### 4-1. 데이터가 읽히는지 확인

```sql
SELECT * FROM week18_firehose_db.bike_status LIMIT 10;
```

✅ 10행이 나오고 `rackTotCnt` 같은 숫자 컬럼에 따옴표가 없으면 성공

### 4-2. 한양대역 1번출구 — 가장 최근 상태

```sql
SELECT stationName, parkingBikeTotCnt, empty_racks, is_empty, polled_at
FROM week18_firehose_db.bike_status
WHERE stationId = 'ST-2327'
ORDER BY polled_at DESC
LIMIT 1;
```

정상 응답 (예시):

| stationName | parkingBikeTotCnt | empty_racks | is_empty | polled_at |
| --- | --- | --- | --- | --- |
| 3545.한양대역 1번출구 | 4 | 6 | false | 2026-11-06T16:25:33+09:00 |

`polled_at`이 몇 분 전 시각이면 실시간 데이터가 맞다.

### 4-3. 한양대 근처 대여소 전부 — 지금 상태

```sql
WITH latest AS (
  SELECT MAX(polled_at) AS t FROM week18_firehose_db.bike_status
)
SELECT b.stationName, b.parkingBikeTotCnt, b.rackTotCnt, b.empty_racks
FROM week18_firehose_db.bike_status b, latest
WHERE b.polled_at = latest.t
  AND b.stationName LIKE '%한양대%'
ORDER BY b.parkingBikeTotCnt DESC;
```

`MAX(polled_at)`으로 가장 최근 폴링 1회분만 골라낸다. 이름에 "한양대"가 들어간 대여소가 모두 나온다.

### 4-4. 한양대역 1번출구 — 최근 1시간 변화

```sql
SELECT substr(polled_at, 12, 5) AS time_kst, parkingBikeTotCnt, empty_racks
FROM week18_firehose_db.bike_status
WHERE stationId = 'ST-2327'
  AND hour IN (cast(hour(current_timestamp AT TIME ZONE 'Asia/Seoul') AS varchar),
               cast(hour(current_timestamp AT TIME ZONE 'Asia/Seoul') - 1 AS varchar))
ORDER BY polled_at;
```

30초마다 한 행씩, 자전거 수가 오르내리는 것이 보인다. `hour IN (...)` 조건 덕분에 최근 2개 시간 폴더만 읽는다.

### 4-5. 서울 전체 — 지금 자전거가 0대인 대여소

```sql
WITH latest AS (
  SELECT MAX(polled_at) AS t FROM week18_firehose_db.bike_status
)
SELECT b.stationName, b.rackTotCnt
FROM week18_firehose_db.bike_status b, latest
WHERE b.polled_at = latest.t
  AND b.is_empty = true
ORDER BY b.rackTotCnt DESC
LIMIT 10;
```

Lambda가 만든 `is_empty` 컬럼 덕분에 조건이 한 줄로 끝난다.

> ⚠️ **오류**
>
> - `SYNTAX_ERROR: Column 'stationid' cannot be resolved` → 컬럼 이름 대소문자 문제. Athena는 대소문자를 구분하지 않으므로 보통 안 나지만, 나면 `"stationId"`처럼 큰따옴표로 감싼다.
> - 결과가 0행 → 3-3 `MSCK REPAIR TABLE`을 안 했거나, 폴러 스케줄이 꺼져서 최근 폴더가 없는 것.
> - `HIVE_BAD_DATA: Error parsing field value` → `clean/` 폴더에 Assignment1 형식(문자열 숫자) 파일이 섞인 것. Assignment2 스트림의 prefix가 `clean/`인지 확인하고, 섞였으면 그 파일을 S3에서 삭제한다.
> - 4-2 결과의 `polled_at`이 30분 넘게 오래됐다면 → 폴러 스케줄이 Disabled인 것. Enable하고 2분 뒤 `MSCK REPAIR TABLE` 후 재조회한다.

## 5. 집계 Lambda 생성

Athena 결과를 대시보드가 읽기 좋은 `data.json` 하나로 만들어 S3에 올리는 함수다. 1분마다 EventBridge가 호출한다.

### 5-1. 웹 버킷 생성

대시보드 파일을 공개할 버킷을 **따로** 만든다. 데이터 버킷은 비공개로 두고, 이 버킷만 공개한다.

1. **S3** → **Create bucket(버킷 만들기)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Bucket name(버킷 이름) | `keulkeul-week18-{ACCOUNT_ID}-{성}-web` | 데이터 버킷 이름 뒤에 `-web` |
| Block all public access(모든 퍼블릭 액세스 차단) | **체크 해제** → 아래 경고 확인 체크 | 팀원이 인터넷으로 접속해야 하므로 공개 |

2. **Create bucket(버킷 만들기)**
3. 만든 버킷 클릭 → **Properties(속성)** 탭 → 맨 아래 **Static website hosting(정적 웹 사이트 호스팅)** → **Edit(편집)**

| 옵션 | 입력값 | 의미 |
| --- | --- | --- |
| Static website hosting | `Enable(활성화)` | |
| Hosting type(호스팅 유형) | `Host a static website(정적 웹 사이트 호스팅)` | |
| Index document(인덱스 문서) | `index.html` | 주소만 쳤을 때 열릴 파일 |

4. **Save changes(변경 사항 저장)** → 같은 섹션에 **Bucket website endpoint** 주소가 생긴다. 메모해 둔다.

```
http://keulkeul-week18-{ACCOUNT_ID}-{성}-web.s3-website.ap-northeast-2.amazonaws.com
```

5. **Permissions(권한)** 탭 → **Bucket policy(버킷 정책)** → **Edit(편집)** → 아래를 붙여넣고 `{ACCOUNT_ID}`, `{성}`을 바꾼 뒤 **Save changes**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicRead",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::keulkeul-week18-{ACCOUNT_ID}-{성}-web/*"
  }]
}
```

✅ Permissions 탭 상단에 "Publicly accessible(퍼블릭 액세스 가능)" 빨간 배지가 보이면 성공 (이 버킷은 의도한 것)

> ⚠️ **오류**
>
> - 버킷 정책 저장 시 `Access Denied` → 1번의 Block all public access를 해제하지 않은 것. Permissions 탭 → Block public access → Edit에서 전부 해제한다.

### 5-2. 대시보드 파일 업로드

1. 웹 버킷 → **Objects(객체)** 탭 → **Upload(업로드)** → 깃허브 `assignment/week16-firehose/web/index.html`을 내려받아 선택 → **Upload**
2. 브라우저에서 5-1의 endpoint 주소를 연다.

✅ "따릉이 실시간 현황" 제목과 흐름도가 보이고, 빨간 박스에 "데이터를 불러오지 못했습니다: data.json 404"가 뜨면 성공. `data.json`은 5-3~5-6의 집계 Lambda가 만든다. 그 전까지는 404가 맞다.

### 5-3. 집계 Lambda 함수 생성

1. 검색창에 **Lambda**를 입력하고 **Lambda**로 이동한다. 리전이 `ap-northeast-2`인지 확인한다.
2. **Create function(함수 생성)** → `Author from scratch(새로 작성)`

| 옵션 | 입력값 |
| --- | --- |
| Function name(함수 이름) | `week18-firehose-aggregator` |
| Runtime(런타임) | `Python 3.12` |

3. **Create function(함수 생성)**
4. **Code(코드)** 탭의 에디터 내용을 전부 지우고 `lambda_aggregator.py` 전체를 붙여넣는다 → **Deploy(배포)**

✅ "Successfully updated the function" 메시지가 뜨면 성공

### 5-4. 환경 변수와 제한 시간

1. **Configuration(구성)** 탭 → 왼쪽 **Environment variables(환경 변수)** → **Edit(편집)** → **Add environment variable(환경 변수 추가)**를 눌러 아래 5개를 모두 넣는다.

| Key | Value | 의미 |
| --- | --- | --- |
| `ATHENA_OUTPUT` | `s3://keulkeul-week18-{ACCOUNT_ID}-{성}/athena-results/` | 2번에서 설정한 결과 위치와 동일. 끝에 `/` 포함 |
| `DATA_BUCKET` | `keulkeul-week18-{ACCOUNT_ID}-{성}` | `clean/`이 있는 데이터 버킷 |
| `WEB_BUCKET` | `keulkeul-week18-{ACCOUNT_ID}-{성}-web` | 5-1에서 만든 웹 버킷. `-web`까지 정확히 |
| `FOCUS_STATIONS` | `ST-2327` | 관심 대여소 |
| `ATHENA_DB` | `week18_firehose_db` | |

2. **Save(저장)**
3. 왼쪽 **General configuration(일반 구성)** → **Edit(편집)** → Timeout(제한 시간) `1` min `0` sec → **Save(저장)**

✅ 환경 변수 목록에 5개, General configuration에 Timeout `1 min 0 sec`이 보이면 성공

### 5-5. Athena·S3 권한 추가

이 함수는 Athena를 호출하고 S3에 쓴다. 기본 실행 역할에는 그 권한이 없으므로 **반드시** 붙인다. 이 단계를 건너뛰면 Test에서 `AccessDenied`가 난다.

1. **Configuration(구성)** 탭 → 왼쪽 **Permissions(권한)**
2. "Execution role(실행 역할)" 아래 역할 이름 `week18-firehose-aggregator-role-...` 클릭 → IAM 화면이 새 탭으로 열린다
3. **Permissions(권한)** 탭 → **Add permissions(권한 추가)** ▼ → **Attach policies(정책 연결)**
4. 검색창에 `AmazonAthenaFullAccess` 입력 → 체크
5. 검색창을 지우고 `AmazonS3FullAccess` 입력 → 체크
6. **Add permissions(권한 추가)**

✅ 역할의 정책 목록에 `AWSLambdaBasicExecutionRole`, `AmazonAthenaFullAccess`, `AmazonS3FullAccess` **3개**가 보이면 성공

### 5-6. 테스트 실행

1. Lambda 함수 화면으로 돌아와 **Test(테스트)** 탭 → Event name(이벤트 이름) `manual` → **Save(저장)** → **Test(테스트)**
2. 10~20초 뒤 결과가 뜬다.

정상 응답:

```
{"statusCode": 200, "polled_at": "2026-11-09T14:12:03+09:00"}
```

3. 브라우저에서 5-1의 endpoint 주소를 새로고침한다.

✅ 빨간 박스가 사라지고 숫자 카드·변화 피드·그래프·지도가 모두 보이면 성공

> ⚠️ **오류**
>
> - `ClientError: An error occurred (AccessDeniedException)` 또는 `AccessDenied` → 5-5를 하지 않은 것. 역할에 정책 2개를 붙이고 다시 Test.
> - `KeyError: 'ATHENA_OUTPUT'` (또는 다른 변수 이름) → 5-4의 환경 변수가 빠진 것. 5개 모두 있는지 확인.
> - `Task timed out after 3.00 seconds` → 5-4의 Timeout을 1분으로 늘리지 않은 것.
> - `NoSuchBucket` → `WEB_BUCKET` 또는 `DATA_BUCKET` 이름 오타. S3 버킷 목록과 글자 단위로 비교.
> - 결과는 200인데 대시보드에 "최근 2시간 안에 완전히 도착한 폴링이 없습니다" → 폴러 스케줄이 꺼져 있거나 `clean/` 폴더가 아직 없는 것. 폴러를 켜고 3분 뒤 다시 Test.
> - 결과는 200인데 대시보드가 여전히 `data.json 404` → `WEB_BUCKET` 값이 웹 버킷이 아니라 데이터 버킷으로 들어간 것. `-web`이 붙어 있는지 확인.
> - 대시보드에 숫자는 뜨는데 지도·그래프가 비어 있다면 → 브라우저가 외부 라이브러리(Chart.js, Leaflet)를 못 받은 것. 인터넷 연결을 확인한다.

### 5-7. EventBridge 스케줄 생성

Assignment1의 6번과 같은 방법으로 만든다. 다른 값만 적는다.

| 옵션 | 입력값 |
| --- | --- |
| Schedule name | `week18-firehose-aggregator-1min` |
| Rate expression | `1` `minutes` |
| Target | `AWS Lambda` → `Invoke` → `week18-firehose-aggregator` |

✅ 2분 뒤 브라우저에서 대시보드 상단 "갱신" 시각이 바뀌고, 30초마다 자동으로 다시 읽히면 성공. 이 URL을 팀원에게 공유한다.

> ⚠️ **중요 — 비용**
>
> 집계 Lambda는 1분마다 Athena 쿼리 3개를 실행한다. Athena는 스캔량 과금이라 하루 종일 켜 두면 수천 원이 나올 수 있다. 발표·시연 때만 Enable하고, 끝나면 폴러 스케줄과 함께 **Disable**한다.

### 5-8. 대시보드 화면 구성

| 영역 | 내용 | 어디서 오는 값인가 |
| --- | --- | --- |
| 흐름도 | Lambda 폴러 → Firehose → Lambda 변환 → S3 → Athena·Lambda 집계 → S3 정적 웹 | 고정 |
| 숫자 카드 | 대여소 수, 전체 자전거, 0대 대여소, 초과 대여소, 누적 레코드, 마지막 수집. 화살표는 **30초 전 대비 증감** | 완전히 도착한 최근 폴링 2회분 비교 |
| 30초 사이에 일어난 일 | 대여 N대 · 반납 N대 · 상태 바뀐 대여소 N곳 + 변화가 큰 대여소 10곳 표 | 두 폴링의 `parkingBikeTotCnt` 차이 |
| 서울 전체 추이 | 전체 자전거 수 · 0대 대여소 수 꺾은선 (최근 3시간) | 폴링별 `SUM`, `COUNT(is_empty)` |
| 관심 대여소 | 한양대역 1번출구 지금 자전거·빈 거치대 + 최근 3시간 꺾은선 | `FOCUS_STATIONS` |
| 지도 | 대여소 2,700개, 빨강 0 · 주황 1~3 · 초록 4+, **흰 테두리 = 방금 바뀐 대여소**. 점을 클릭하면 아래에 상세 | 위경도 컬럼 |

30초마다 `data.json`을 다시 읽어 자동 갱신되고, 상단 **지금 새로고침** 버튼으로 즉시 갱신할 수도 있다. `data.json` 자체는 집계 Lambda가 1분마다 바꾼다.

### 5-9. 집계 Lambda에서 확인할 항목

| 항목 | 값 | 역할 |
| --- | --- | --- |
| Function name | `week18-firehose-aggregator` | 1분마다 실행 |
| 환경 변수 | `ATHENA_OUTPUT`, `DATA_BUCKET`, `WEB_BUCKET`, `FOCUS_STATIONS`, `ATHENA_DB` | 입력·출력 위치 |
| 실행 역할 정책 | `AmazonAthenaFullAccess`, `AmazonS3FullAccess` | Athena 조회 + S3 쓰기 |
| 웹 버킷 | 정적 웹 호스팅 + 퍼블릭 읽기 정책 | 팀원 접속 |

## 6. (대안) 노트북에서 대시보드 띄우기 — 시간이 없을 때

5번(S3 정적 웹 배포)을 할 시간이 없으면, 같은 대시보드를 **노트북에서 Streamlit으로** 띄워 발표 화면으로만 보여준다. Athena 테이블(3번)까지만 되어 있으면 된다. 팀원이 URL로 접속하는 건 안 되고, 발표자 화면 공유로 본다.

제공 파일: `dashboard.py`

### 6-1. 노트북용 IAM 사용자와 액세스 키

노트북의 파이썬이 Athena를 호출하려면 자격 증명이 필요하다.

1. **IAM** → **Users(사용자)** → **Create user(사용자 생성)**

| 옵션 | 입력값 |
| --- | --- |
| User name(사용자 이름) | `week18-dashboard-local` |
| Provide user access to the AWS Management Console | 체크 해제 (기본값) |

→ **Next(다음)**

| 옵션 | 입력값 |
| --- | --- |
| Permissions options(권한 옵션) | `Attach policies directly(직접 정책 연결)` |
| 검색창 | `AmazonAthenaFullAccess` 체크 → 지우고 `AmazonS3FullAccess` 체크 |

→ **Next(다음)** → **Create user(사용자 생성)**

2. 생성된 사용자 클릭 → **Security credentials(보안 자격 증명)** 탭 → **Create access key(액세스 키 만들기)**
3. Use case: `Command Line Interface (CLI)` → 확인 체크 → **Next** → **Create access key**
4. **Download .csv file**로 키를 저장한다. 이 화면을 닫으면 Secret은 다시 볼 수 없다.

> ⚠️ **중요**
>
> Access Key는 비밀번호와 같다. 깃허브·노션·카톡에 올리지 않는다. 발표가 끝나면 6-4에서 삭제한다.

### 6-2. 노트북 설정

터미널(CMD 또는 PowerShell)에서:

```
pip install streamlit pandas boto3 pydeck altair
aws configure
```

`aws configure`에서 순서대로 입력한다.

```
AWS Access Key ID: {csv의 Access key ID}
AWS Secret Access Key: {csv의 Secret access key}
Default region name: ap-northeast-2
Default output format: json
```

AWS CLI가 없다면 메모장으로 `C:\Users\{윈도우사용자}\.aws\credentials` 파일을 만들고 아래를 저장한다 (확장자 없음).

```
[default]
aws_access_key_id = {Access key ID}
aws_secret_access_key = {Secret access key}
region = ap-northeast-2
```

### 6-3. 실행

깃허브 `assignment/week16-firehose` 폴더를 내려받은 뒤 그 폴더에서:

```
streamlit run dashboard.py
```

처음 실행하면 `Email:` 입력란이 나온다. 비워 둔 채 **엔터**. 브라우저가 `http://localhost:8501`로 열린다.

사이드바(왼쪽 위 `»`)의 **Athena 결과 위치**가 `s3://keulkeul-week18-{ACCOUNT_ID}-{성}/athena-results/`로 자동 채워졌는지 확인한다. 비어 있으면 직접 입력한다.

✅ 숫자 카드·"30초 사이에 일어난 일"·그래프·지도가 보이면 성공. 30초마다 자동 갱신된다. 화면 구성은 5-8과 같다.

> ⚠️ **오류**
>
> - `NoCredentialsError: Unable to locate credentials` → 6-2의 자격 증명 파일 위치나 이름이 틀린 것. `credentials.txt`로 저장되지 않았는지 확인.
> - `AccessDeniedException ... athena:StartQueryExecution` → 6-1에서 정책을 안 붙인 것.
> - `최근 2시간 안에 완전히 도착한 폴링이 없습니다` → 폴러 스케줄이 꺼져 있거나 `MSCK REPAIR TABLE`을 안 한 것.
> - 지도 점을 클릭해도 상세가 안 바뀜 → `pip install -U streamlit` 후 재실행 (1.39 이상 필요).

### 6-4. 발표 후 정리

- 터미널에서 `Ctrl + C`로 대시보드 종료
- **IAM** → **Users** → `week18-dashboard-local` → Security credentials → 액세스 키 **삭제** → 사용자 **삭제**

## 7. 리소스 정리 (전체 실습 종료 후)

> 💡 **왜 검색으로 지우나**
>
> Firehose 스트림이나 Lambda 함수를 지워도 그때 자동 생성된 **IAM 역할은 남는다.** 생성에 실패했던 시도에서도 역할은 생긴다. 그래서 "내가 만든 것"을 기억해서 지우는 게 아니라, 각 콘솔 검색창에 `week18`을 넣어 **나오는 것을 전부** 지운다. 리전이 있는 서비스는 **서울과 버지니아 둘 다** 확인한다 (실습 중 리전이 바뀌었을 수 있다).

삭제는 아래 순서대로 한다. 앞 단계를 먼저 지워야 뒤 단계가 지워지는 의존 관계가 있다.

### 6-1. EventBridge 스케줄

1. **EventBridge** → **Scheduler** → **Schedules** → 검색창 `week18`
2. 나오는 것 전부 체크 → **Delete** → 확인 입력
3. 리전을 **버지니아(us-east-1)** 로 바꿔 같은 검색 → 있으면 삭제

### 6-2. Lambda 함수

1. **Lambda** → **Functions** → 검색창 `week18`
2. 나오는 것 전부 체크 (`week18-firehose-poller`, `week18-firehose-transform`, `week18-firehose-aggregator`) → **Actions** → **Delete** → 확인 입력
3. 버지니아 리전에서도 같은 검색 → 있으면 삭제

### 6-3. Firehose 스트림

1. **Amazon Data Firehose** → 검색창 `week18`
2. 나오는 것 전부 → **Delete** → 이름 입력
3. 버지니아 리전에서도 같은 검색 → 있으면 삭제

### 6-4. Athena

쿼리 편집기에서 한 줄씩 실행한다.

```sql
DROP TABLE IF EXISTS week18_firehose_db.bike_status;
DROP DATABASE IF EXISTS week18_firehose_db;
```

### 6-5. S3 버킷

버킷은 비워야 지워진다. 버킷 2개 모두:

1. **S3** → 검색창 `week18` → 버킷 체크 → **Empty(비우기)** → `permanently delete` 입력 → **Empty**
2. 같은 버킷 체크 → **Delete(삭제)** → 버킷 이름 입력 → **Delete bucket**

### 6-6. IAM 역할 (가장 많이 남는 곳)

**IAM** → **Roles(역할)** → 검색창에 아래 네 가지를 **차례로** 넣고, 나오는 것 전부 체크 → **Delete** → 이름 입력

| 검색어 | 무엇이 나오나 | 몇 개 나올 수 있나 |
| --- | --- | --- |
| `week18` | Lambda 함수 3개의 실행 역할 (`week18-firehose-*-role-*`) | 3개 이상 (함수를 다시 만들었으면 더) |
| `KinesisFirehoseServiceRole-week18` | Firehose 스트림이 만든 역할 | 2개 이상 (실패한 시도마다 1개씩 더, `us-east-1`이 든 것 포함) |
| `Amazon_EventBridge_Scheduler` | 스케줄이 만든 역할 | 2개 이상 |
| `week18` (Users 메뉴) | 6번 대안을 했다면 IAM **사용자** `week18-dashboard-local` | **Users(사용자)** 메뉴에서 검색. 액세스 키 삭제 → 사용자 삭제 |

✅ 네 검색어 모두 결과가 0건이면 성공

> ⚠️ **오류**
>
> - 역할 삭제 시 "role is in use" → 그 역할을 쓰는 Lambda·Firehose·스케줄이 아직 남아 있는 것. 6-1~6-3을 먼저 끝낸다.
> - `AWSServiceRoleFor...`로 시작하는 역할은 AWS가 관리하는 것이라 지우지 않아도 된다 (검색어에 안 걸린다).

### 6-7. CloudWatch 로그 그룹 (선택, 용량 과금 소액)

1. **CloudWatch** → **Log groups** → 검색창 `week18`
2. 나오는 것 전부 체크 (`/aws/lambda/week18-*`, `/aws/kinesisfirehose/week18-*`) → **Actions** → **Delete log group(s)**
3. 버지니아 리전에서도 같은 검색

### 6-8. 최종 확인

아래 콘솔 검색창에 `week18`을 넣어 **아무것도 안 나오면** 끝. 서울·버지니아 둘 다.

- Lambda / Amazon Data Firehose / EventBridge Scheduler / S3 / CloudWatch Log groups / IAM Roles / IAM Users

> ⚠️ **중요**
>
> 스케줄 두 개를 켜 둔 채 잊으면 하루 수백 MB씩 쌓이고 Athena 비용도 발생한다. 전부 지우지 않더라도 EventBridge 스케줄은 반드시 **Disable** 한다.
