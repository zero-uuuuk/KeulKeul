## Assignment: S3에서 React 정적 웹 사이트 구성하기

React + Vite로 만든 CSR 앱을 빌드하고, 생성된 정적 파일을 S3 정적 웹 사이트 호스팅으로 배포한다.

참고 자료:
- https://docs.aws.amazon.com/ko_kr/AmazonS3/latest/userguide/HostingWebsiteOnS3Setup.html
- https://tech.cloud.nongshim.co.kr/blog/aws/3469/

> [!NOTE]
> S3 정적 웹 사이트 호스팅은 서버 코드를 실행하지 않고 HTML, JavaScript, CSS 같은 정적 파일만 제공한다. 
> CSR(Client-Side Rendering)은 브라우저가 JavaScript를 실행해 화면을 구성하므로 배포할 수 있지만, SSR(Server-Side Rendering)은 요청마다 서버에서 코드를 실행해야 하므로 S3 단독으로는 배포할 수 없다.
> 이번 실습에서는 CSR(React + Vite)을 사용한다.

> [!IMPORTANT]
> 이번 실습에서는 S3 웹 사이트 엔드포인트를 직접 사용하기 위해 버킷의 퍼블릭 읽기 접근을 허용한다. 실습이 끝나면 반드시 리소스를 삭제한다.

> [!IMPORTANT]
> S3 정적 웹 사이트 엔드포인트는 `HTTP`만 지원한다. `HTTPS`가 필요한 실제 서비스에서는 CloudFront를 S3 앞단에 두는 구성이 필요하다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한 (S3)
- Node.js 및 npm
- 제공된 React + Vite 앱: https://github.com/zero-uuuuk/KeulKeul/tree/main/assignment/week3-s3/level2-static-website/app

## 1. React 앱 로컬 실행

먼저 제공된 CSR 앱이 로컬에서 정상 동작하는지 확인한다.

```bash
cd assignment/week3-s3/level2-static-website/app
npm install
npm run dev
```
브라우저에서 터미널에 표시된 local URL로 접속한다.

확인할 것:

- `React CSR on Amazon S3` 제목이 보이는가?
- 탭 버튼을 눌렀을 때 페이지 전체가 새로고침되지 않고 아래 설명 내용만 바뀌는가?
- 이 화면 전환이 서버 요청이 아니라 브라우저의 JavaScript 상태 변경으로 처리된다는 점을 이해했는가?

## 2. 배포 파일 빌드

Vite build 명령으로 S3에 업로드할 정적 파일을 만든다.

```bash
npm run build
```

생성되는 폴더:

```text
dist/
```

확인할 것:

- `dist/index.html` 파일이 생성되었는가?
- `dist/assets/` 아래에 JavaScript와 CSS 파일이 생성되었는가?
- 브라우저가 `index.html`을 받은 뒤 `assets`의 JS/CSS를 추가로 내려받아 화면을 구성한다는 점을 이해했는가?

> [!NOTE]
> S3에는 React 소스 코드인 `src/`를 올리는 것이 아니라, build 결과물인 `dist/` 안의 파일을 올린다.

## 3. S3 버킷 생성

정적 웹 사이트 파일을 저장할 S3 버킷을 만든다.

1. AWS 콘솔 → **S3** → **버킷 만들기** 클릭
2. 설정값:
    - 버킷 이름: 전 세계에서 고유한 이름 입력 (예: `keulkeul-week3-static-website-{본인이름}`)
    - AWS 리전: 원하는 리전 선택
    - 객체 소유권, 버킷 버전 관리, 기본 암호화: 기본값 유지
    - **퍼블릭 액세스 차단 설정**: 일단 기본값 유지
3. **버킷 만들기** 클릭

## 4. 정적 웹 사이트 호스팅 활성화

S3 버킷을 단순 파일 저장소가 아니라 웹 사이트처럼 응답하도록 설정한다.

1. 생성한 버킷 선택
2. **속성** 탭으로 이동
3. 아래쪽의 **정적 웹 사이트 호스팅**에서 **편집** 클릭
4. 설정값:
    - 정적 웹 사이트 호스팅: `활성화`
    - 호스팅 유형: `정적 웹 사이트 호스팅`
    - 인덱스 문서: `index.html`
    - 오류 문서: `index.html`
5. **변경 사항 저장** 클릭
6. **정적 웹 사이트 호스팅** 영역에 표시되는 **버킷 웹 사이트 엔드포인트**를 복사해둔다.

> [!NOTE]
> 오류 문서를 `index.html`로 두면 존재하지 않는 경로로 직접 접속했을 때도 React 앱의 시작 파일을 반환한다.

## 5. 빌드 결과물 업로드

`dist/` 폴더 안의 파일과 폴더를 S3 버킷 루트에 업로드한다.

콘솔에서 업로드:

1. 버킷의 **객체** 탭으로 이동
2. **업로드** 클릭
3. `dist/` 폴더 안의 `index.html`과 `assets/` 폴더 추가
4. **업로드** 클릭

업로드 후 확인할 것:

- 버킷 루트에 `index.html`이 있는가?
- 버킷에 `assets/` 폴더와 JS/CSS 파일이 있는가?
- `dist` 폴더 자체가 아니라 `dist` 안의 내용이 올라갔는가?

## 6. 퍼블릭 액세스 차단 해제

브라우저에서 S3 웹 사이트 파일을 읽을 수 있도록 버킷의 퍼블릭 액세스 차단 설정을 수정한다.

1. 버킷의 **권한** 탭으로 이동
2. **퍼블릭 액세스 차단(버킷 설정)**에서 **편집** 클릭
3. **모든 퍼블릭 액세스 차단** 체크 해제
4. 경고 문구를 확인한 뒤 **변경 사항 저장** 클릭
5. 확인 입력창이 나오면 안내에 따라 입력 후 저장

> [!IMPORTANT]
> 이 설정만으로 객체가 바로 공개되는 것은 아니다. 다음 단계에서 버킷 정책으로 `s3:GetObject` 권한을 허용해야 한다.

## 7. 버킷 정책 추가

버킷 안의 웹 사이트 파일을 인터넷에서 읽을 수 있도록 퍼블릭 읽기 정책을 추가한다.

1. 버킷의 **권한** 탭으로 이동
2. **버킷 정책**에서 **편집** 클릭
3. 아래 정책을 붙여넣고 `{BUCKET_NAME}`을 실제 버킷 이름으로 교체

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::{BUCKET_NAME}/*"
    }
  ]
}
```

4. **변경 사항 저장** 클릭

> [!NOTE]
> `Policy has invalid resource` 오류가 나오면 `Resource`의 버킷 이름이 실제 버킷 이름과 같은지 확인한다.

## 8. 웹 사이트 endpoint 테스트

4장에서 복사한 S3 웹 사이트 endpoint로 접속해 React 앱이 열리는지 확인한다.

브라우저에서 확인:

```text
http://{BUCKET_WEBSITE_ENDPOINT}
```

확인할 것:

- 브라우저에서 React 앱 화면이 보이는가?
- 개발자 도구 Network 탭에서 `index.html`, JS, CSS 파일을 S3에서 내려받는가?
- `https://`에서는 작동안하고, `http://`에서만 작동하는가?

## 9. 실습 질문

아래 질문에 짧게 답한다.

1. 이번 React + Vite 앱을 CSR이라고 부를 수 있는 이유는 무엇인가?
2. S3에 `src/`가 아니라 `dist/`를 업로드해야 하는 이유는 무엇인가?
3. Vite build 결과에서 `index.html`과 `assets/`는 각각 어떤 역할을 하는가?
4. 퍼블릭 액세스 차단을 해제했는데도 버킷 정책이 필요한 이유는 무엇인가?
5. S3 정적 웹 사이트 endpoint가 HTTPS를 직접 지원하지 않는다는 점은 실제 서비스에서 어떤 제약이 되는가?

## 10. 리소스 정리

실습 완료 후 아래 순서로 리소스를 삭제한다.

1. **S3 객체 삭제**
    - 버킷에 업로드한 `index.html`, `assets/` 객체 삭제

2. **S3 버킷 삭제**
    - 버킷 목록에서 실습용 버킷 선택
    - **삭제** 클릭
    - 안내에 따라 버킷 이름 입력 후 삭제

> [!NOTE]
> 버킷 안에 객체가 남아 있으면 버킷 삭제가 실패한다. 먼저 버킷을 비운 뒤 삭제한다.
