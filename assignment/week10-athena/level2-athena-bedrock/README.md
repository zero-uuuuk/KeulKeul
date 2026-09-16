# Level 2: EC2와 Athena, OpenAI로 OTT 시청 로그 분석

OTT 웹 서버를 EC2에 배포하고, 로컬 스크립트로 실제 시청 요청 10,000건을 보낸 뒤, 웹 화면의 분석 실행 버튼 하나로 S3 → Athena → OpenAI 워크플로를 실행한다.

핵심 흐름:

```text
traffic.py (로컬)
-> EC2 웹 서버가 JSON Lines 로그 기록
-> 분석 실행 버튼
-> S3 업로드
-> Athena External Table 생성 및 집계 쿼리
-> OpenAI Chat Completions 리포트
-> 웹 화면에 한국어 분석 결과
```

폴더 구조:

```text
level2-athena-bedrock/
├── app/                  EC2에 배포되는 웹 서버
│   ├── app.py            시청 이벤트 기록과 분석 작업 API
│   ├── analysis.py       S3 업로드, Athena 쿼리, OpenAI 호출 워크플로
│   ├── index.html        작품 카드, 진행 상태, 분석 리포트 화면
│   ├── requirements.txt  boto3
│   └── .env.example      OPENAI_API_KEY 작성 예시
└── traffic/              로컬에서 실행하는 스크립트
    └── traffic.py        원격 서버에 시청 요청 대량 전송
```

`app`은 EC2에서 systemd 서비스로 실행되고, `traffic`은 로컬 터미널에서만 실행한다. `traffic.py`는 Python 표준 라이브러리만 사용하므로 별도 설치가 없다.

자세한 진행은 `assignment.md`를 따른다.
