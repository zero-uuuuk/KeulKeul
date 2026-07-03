## Assignment: S3 콘솔에서 Presigned URL로 private 파일 공유하기

S3 버킷은 private으로 유지하고, S3 콘솔에서 presigned URL을 생성해 제한 시간 동안만 파일을 다운로드할 수 있게 공유한다.

참고 자료: https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html

> [!NOTE]
> 이번 레벨에서는 S3 bucket policy로 객체를 public으로 열지 않는다. 파일 접근은 presigned URL을 통해서만 허용한다.

> [!IMPORTANT]
> presigned URL은 URL 자체가 임시 접근 권한처럼 동작한다. 만료 전에는 URL을 아는 사람이 사용할 수 있으므로 공개된 곳에 올리지 않는다.

## 0. 사전 준비

- AWS 계정 및 IAM 권한 (S3)
- 공유 테스트에 사용할 작은 파일

## 1. S3 버킷 생성  

presigned URL로 공유할 private S3 버킷을 만든다.

1. AWS 콘솔 → **S3** → **버킷 만들기** 클릭
2. 설정값:
    - 버킷 이름: 전 세계에서 고유한 이름 입력 (예: `keulkeul-week3-presigned-{본인이름}`)
    - AWS 리전: 원하는 리전 선택
    - 객체 소유권, 버킷 버전 관리, 기본 암호화: 기본값 유지
    - **퍼블릭 액세스 차단 설정**: 모든 퍼블릭 액세스 차단 켬
3. **버킷 만들기** 클릭

> [!IMPORTANT]
> 이번 실습 버킷은 public으로 열지 않는다. 일반 S3 객체 URL로 접근했을 때 `AccessDenied`가 나와야 정상이다.

## 2. 파일 업로드  

private 버킷에 공유할 파일을 업로드한다.

1. 1장에서 만든 S3 버킷 선택
2. **업로드** 클릭
3. 임의의 작은 파일 선택
    - 예: `hello.txt`, `profile.png`, `report.pdf`
4. **업로드** 클릭

업로드 후 확인할 것:

- 버킷 객체 목록에 업로드한 파일이 보이는가?
- 객체를 선택했을 때 object URL이 보이는가?
- object URL을 새 브라우저 탭에서 열면 `AccessDenied` 또는 `403 Forbidden`이 나오는가?

## 3. Presigned URL 생성  

업로드한 객체를 제한 시간 동안 다운로드할 수 있는 presigned URL을 만든다.

1. S3 버킷의 **객체** 탭으로 이동
2. 2장에서 업로드한 객체 선택
3. **작업** 메뉴 클릭
4. **Presigned URL로 공유** 선택
5. 만료 시간 입력:
    - 예: `2분`
6. **Presigned URL 생성** 클릭
7. 생성된 URL을 복사해둔다.

## 4. Presigned URL로 다운로드 확인

3장에서 복사한 presigned URL을 새 브라우저 탭이나 핸드폰에서 열어 파일을 다운로드한다.

확인할 것:

- URL 만료 전에는 파일을 다운로드할 수 있는가?
- 같은 객체의 일반 object URL은 여전히 접근이 차단되는가?
- URL을 AWS 계정에 로그인하지 않은 다른 브라우저나 시크릿 창에서 열어도 다운로드되는가?

> [!NOTE]
> presigned URL은 AWS 로그인 여부가 아니라 URL에 포함된 임시 서명으로 접근을 허용한다. 그래서 URL을 받은 사람은 만료 전까지 AWS 계정 없이도 파일을 다운로드할 수 있다.

## 5. 만료 후 접근 확인

3장에서 설정한 만료 시간이 지난 뒤 같은 presigned URL을 다시 열어본다.

확인할 것:

- 만료 시간이 지나면 같은 URL로 더 이상 다운로드할 수 없는가?
- 만료된 URL을 다시 살릴 수 없고 새 presigned URL을 발급해야 한다는 점을 이해했는가?
- 만료 시간을 길게 설정하면 URL이 유출되었을 때 위험 시간이 길어진다는 점을 이해했는가?

> [!IMPORTANT]
> presigned URL은 발급 후 URL 자체만 골라서 회수하기 어렵다. 공유를 즉시 중단해야 한다면 객체를 삭제하거나 이름을 바꾸는 방식으로 접근을 막을 수 있다.

## 6. 실습 질문

아래 질문에 짧게 답한다.

1. presigned URL을 사용하면 S3 버킷을 public으로 열지 않아도 파일을 공유할 수 있는 이유는 무엇인가?
2. 일반 object URL은 실패하는데 presigned URL은 성공하는 이유는 무엇인가?
3. presigned URL을 AWS 계정에 로그인하지 않은 브라우저에서도 사용할 수 있는 이유는 무엇인가?
4. presigned URL 만료 시간을 길게 설정하면 어떤 보안 문제가 생길 수 있는가?
5. 파일을 더 이상 공유하고 싶지 않을 때 URL 자체를 회수할 수 없다면 어떤 방법으로 접근을 막을 수 있는가?

## 7. 리소스 정리

실습 완료 후 아래 순서로 리소스를 삭제한다.

1. **S3 객체 삭제**
    - 실습 중 업로드한 객체 삭제

2. **S3 버킷 삭제**
    - 버킷 비우기 후 버킷 삭제
