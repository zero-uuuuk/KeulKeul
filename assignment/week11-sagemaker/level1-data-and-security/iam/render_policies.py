"""Render IAM JSON locally. This does not create or change AWS resources."""
import argparse
import json
import re
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--account-id',required=True)
    p.add_argument('--bucket',required=True)
    a=p.parse_args()
    if not re.fullmatch(r'\d{12}',a.account_id): raise ValueError('12 digit account ID required')
    if not re.fullmatch(r'keulkeul-week11-'+a.account_id+r'-[a-z0-9-]+',a.bucket):
        raise ValueError('Use keulkeul-week11-ACCOUNT_ID-suffix')
    role=f'arn:aws:iam::{a.account_id}:role/keulkeul-week11-sagemaker-role'
    bucket='arn:aws:s3:::'+a.bucket
    region='ap-northeast-2'
    def allow(actions,resources,**kwargs):
        return dict(Effect='Allow',Action=actions,Resource=resources,**kwargs)
    s3=[allow(['s3:GetBucketLocation','s3:ListBucket'],bucket),
        allow(['s3:GetObject','s3:PutObject','s3:AbortMultipartUpload'],bucket+'/week11/*')]
    execution={'Version':'2012-10-17','Statement':s3+[
        allow(['ecr:GetAuthorizationToken'],'*'),
        allow(['ecr:BatchCheckLayerAvailability','ecr:GetDownloadUrlForLayer','ecr:BatchGetImage'],
              'arn:aws:ecr:ap-northeast-2:366743142698:repository/sagemaker-xgboost'),
        allow(['logs:CreateLogGroup','logs:CreateLogStream','logs:PutLogEvents','logs:DescribeLogStreams'],
              [f'arn:aws:logs:{region}:{a.account_id}:log-group:/aws/sagemaker/*',
               f'arn:aws:logs:{region}:{a.account_id}:log-group:/aws/sagemaker/*:*']),
        allow(['cloudwatch:PutMetricData'],'*'),
    ]}
    resources=[f'arn:aws:sagemaker:{region}:{a.account_id}:{kind}/keulkeul-w11-*'
               for kind in ['training-job']]
    operator={'Version':'2012-10-17','Statement':s3+[
        allow(['sagemaker:Search'],'*'),
        allow(['sagemaker:CreateTrainingJob','sagemaker:DescribeTrainingJob','sagemaker:StopTrainingJob','sagemaker:AddTags'],resources),
        allow(['iam:GetRole'],role),
        allow(['iam:PassRole'],role,Condition={'StringEquals':{'iam:PassedToService':'sagemaker.amazonaws.com'}}) ]}
    trust={'Version':'2012-10-17','Statement':[{'Effect':'Allow',
        'Principal':{'Service':'sagemaker.amazonaws.com'},'Action':'sts:AssumeRole',
        'Condition':{'StringEquals':{'aws:SourceAccount':a.account_id},
                     'ArnLike':{'aws:SourceArn':f'arn:aws:sagemaker:{region}:{a.account_id}:*'}}}]}
    out=Path(__file__).resolve().parent/'rendered'; out.mkdir(exist_ok=True)
    for name,policy in [('trust.json',trust),('execution-policy.json',execution),
                        ('operator-policy.json',operator)]:
        (out/name).write_text(json.dumps(policy,indent=2),encoding='utf-8')
    print('Created iam/rendered/*.json locally; apply through the console per assignment.')

if __name__=='__main__': main()
