import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def load_config(path=None, require_kb=False):
    path=Path(path) if path else ROOT/'config.json'
    if not path.exists():
        raise ValueError('먼저 python -m lab.cli init으로 개인 설정을 만드세요.')
    c=json.loads(path.read_text(encoding='utf-8-sig'))
    if not re.fullmatch(r'\d{12}',c.get('account_id','')):
        raise ValueError('자신의 12자리 AWS 계정 ID가 필요합니다.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,11}',c.get('suffix','')):
        raise ValueError('suffix는 영문 소문자·숫자·하이픈 2~12자입니다.')
    if c.get('region')!='ap-northeast-2':
        raise ValueError('공통 실습은 서울 ap-northeast-2 기준입니다.')
    if not c.get('profile') or not c.get('model_id'):
        raise ValueError('AWS profile과 model_id를 지정하세요.')
    stem=f"keulkeul-bedrock-{c['account_id']}-{c['suffix']}"
    names={'bucket':stem,'vector_bucket':stem,'vector_index':'documents',
           'service_role':f"KeulkeulBedrockKB-{c['suffix']}"}
    for key,value in names.items():
        if c.get(key) not in ('',None,value):
            raise ValueError('임의의 공유 자원을 지정할 수 없습니다: '+key)
        c[key]=value
    if require_kb and not all(c.get(key) for key in ['knowledge_base_id','data_source_id']):
        raise ValueError('콘솔에서 만든 KB ID와 data source ID를 설정하세요.')
    return c


def init_config(account,suffix,profile):
    target=ROOT/'config.json'
    if target.exists():
        raise ValueError('config.json이 이미 있습니다. 덮어쓰지 않았습니다.')
    c=json.loads((ROOT/'config.example.json').read_text(encoding='utf-8'))
    c.update(account_id=account,suffix=suffix,profile=profile)
    candidate=ROOT/'.config-candidate.json'
    try:
        candidate.write_text(json.dumps(c,indent=2),encoding='utf-8')
        c=load_config(candidate)
    finally:
        candidate.unlink(missing_ok=True)
    target.write_text(json.dumps(c,indent=2),encoding='utf-8')
    return c
