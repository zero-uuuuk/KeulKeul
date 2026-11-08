import json
from .config import ROOT


def upload(c,s3):
    source=ROOT/'data/lab-guide.txt'
    metadata=ROOT/'data/lab-guide.txt.metadata.json'
    text=source.read_text(encoding='utf-8')
    meta=json.loads(metadata.read_text(encoding='utf-8'))
    attrs=meta.get('metadataAttributes',{})
    if not text.strip() or attrs.get('doc_id')!='lab-guide-v1':
        raise ValueError('실습 문서와 doc_id 메타데이터를 확인하세요.')
    if len(json.dumps(attrs,ensure_ascii=False).encode('utf-8'))>950:
        raise ValueError('메타데이터가 실습 크기 상한을 초과했습니다.')
    s3.head_bucket(Bucket=c['bucket'],ExpectedBucketOwner=c['account_id'])
    for path,content_type in [(source,'text/plain; charset=utf-8'),(metadata,'application/json')]:
        s3.put_object(Bucket=c['bucket'],Key='docs/'+path.name,Body=path.read_bytes(),
                      ContentType=content_type,ExpectedBucketOwner=c['account_id'])
    print('실습 TXT와 metadata 두 객체를 docs/에 업로드했습니다. 검색 반영에는 Sync가 필요합니다.')
