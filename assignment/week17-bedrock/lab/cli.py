import argparse
import json
from datetime import datetime,timezone
from .config import ROOT,init_config,load_config


def main():
    parser=argparse.ArgumentParser(description='Bedrock: Converse, Knowledge Base Retrieve, RAG')
    commands=parser.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init',help='로컬 설정·정책 생성, AWS 호출 없음')
    init.add_argument('--account',required=True)
    init.add_argument('--suffix',required=True)
    init.add_argument('--profile',default='keulkeul-bedrock')
    for name in ['plan','render-policies','check']:
        commands.add_parser(name)
    for name in ['prepare','upload','sync']:
        commands.add_parser(name).add_argument('--apply',action='store_true')
    for name in ['generate','retrieve','rag']:
        command=commands.add_parser(name)
        command.add_argument('question')
        if name!='retrieve':
            command.add_argument('--max-tokens',type=int,default=256)
            command.add_argument('--temperature',type=float,default=0)
        if name!='generate':
            command.add_argument('--top-k',type=int,default=3)
    args=parser.parse_args()
    if args.command=='init':
        from .iam import render
        render(init_config(args.account,args.suffix,args.profile))
        print('로컬 설정·정책 파일 생성 완료. AWS에 정책이나 자원을 만들지는 않았습니다.')
        return 0
    c=load_config(require_kb=args.command in ['check','sync','retrieve','rag'])
    if args.command=='render-policies':
        from .iam import render
        render(c)
        return 0
    if args.command in ['plan','prepare']:
        from .storage import plan,prepare
        print(json.dumps(plan(c),ensure_ascii=False,indent=2))
        if args.command=='plan' or not args.apply:
            print('계획만 표시했습니다. prepare --apply일 때 저장소·역할을 생성합니다.')
            return 0
    if args.command in ['upload','sync'] and not args.apply:
        print('실행하지 않았습니다. --apply를 붙이면 '+('실습 두 객체를 S3에 업로드합니다.' if args.command=='upload' else '수집·임베딩 작업을 시작합니다.'))
        return 0
    from .aws import session_for,client
    session=session_for(c)
    if args.command=='prepare':
        prepare(c,session)
    elif args.command=='upload':
        from .documents import upload
        upload(c,client(session,'s3'))
    elif args.command=='sync':
        from .storage import sync
        print('Sync 완료:',sync(c,client(session,'bedrock-agent')).get('statistics',{}))
    elif args.command=='check':
        from .storage import check
        print(json.dumps(check(c,client(session,'bedrock-agent'),client(session,'s3')),ensure_ascii=False))
    else:
        from .lesson import generate,retrieve,rag,markdown_result
        if args.command=='generate':
            result=generate(c,client(session,'bedrock-runtime'),args.question,
                            max_tokens=args.max_tokens,temperature=args.temperature)
        elif args.command=='retrieve':
            result=retrieve(c,client(session,'bedrock-agent-runtime'),args.question,top_k=args.top_k)
        else:
            result=rag(c,client(session,'bedrock-agent-runtime'),client(session,'bedrock-runtime'),
                       args.question,top_k=args.top_k,max_tokens=args.max_tokens,temperature=args.temperature)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        folder=ROOT/'outputs'/f"{args.command}-{stamp}"
        folder.mkdir(parents=True)
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'result.md').write_text(markdown_result(result),encoding='utf-8')
        print(markdown_result(result));print('저장:',folder)
        return 0 if result['status'] in ['generated','retrieved'] else 1
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (Exception,KeyboardInterrupt) as exc:
        code=getattr(exc,'response',{}).get('Error',{}).get('Code',type(exc).__name__)
        print(f'실행 중단 ({code}): {exc}')
        raise SystemExit(1)
