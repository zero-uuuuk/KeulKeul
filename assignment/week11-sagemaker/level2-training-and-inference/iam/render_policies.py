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
        allow(['ec2:CreateNetworkInterface','ec2:CreateNetworkInterfacePermission','ec2:DeleteNetworkInterface',
               'ec2:DeleteNetworkInterfacePermission','ec2:DescribeNetworkInterfaces','ec2:DescribeVpcs',
               'ec2:DescribeSubnets','ec2:DescribeDhcpOptions','ec2:DescribeSecurityGroups','ec2:DescribeVpcEndpoints'],'*') ]}
    resources=[f'arn:aws:sagemaker:{region}:{a.account_id}:{kind}/keulkeul-w11-*'
               for kind in ['training-job','model','endpoint-config','endpoint']]
    operator={'Version':'2012-10-17','Statement':s3+[
        allow(['sagemaker:Search'],'*'),
        allow(['sagemaker:CreateTrainingJob','sagemaker:DescribeTrainingJob','sagemaker:StopTrainingJob',
               'sagemaker:CreateModel','sagemaker:DescribeModel','sagemaker:DeleteModel',
               'sagemaker:CreateEndpointConfig','sagemaker:DescribeEndpointConfig','sagemaker:DeleteEndpointConfig',
               'sagemaker:CreateEndpoint','sagemaker:DescribeEndpoint','sagemaker:DeleteEndpoint',
               'sagemaker:InvokeEndpoint','sagemaker:AddTags'],resources),
        allow(['iam:GetRole'],role),
        allow(['iam:PassRole'],role,Condition={'StringEquals':{'iam:PassedToService':'sagemaker.amazonaws.com'}}),
        allow(['ec2:DescribeSubnets','ec2:DescribeSecurityGroups','ec2:DescribeRouteTables','ec2:DescribeVpcEndpoints'],'*') ]}
    trust={'Version':'2012-10-17','Statement':[{'Effect':'Allow',
        'Principal':{'Service':'sagemaker.amazonaws.com'},'Action':'sts:AssumeRole',
        'Condition':{'StringEquals':{'aws:SourceAccount':a.account_id},
                     'ArnLike':{'aws:SourceArn':f'arn:aws:sagemaker:{region}:{a.account_id}:*'}}}]}
    endpoint={'Version':'2012-10-17','Statement':[dict(allow(
        ['s3:GetObject','s3:PutObject','s3:ListBucket','s3:GetBucketLocation','s3:AbortMultipartUpload'],
        [bucket,bucket+'/week11/*']),Principal='*')]}
    out=Path(__file__).resolve().parent/'rendered'; out.mkdir(exist_ok=True)
    for name,policy in [('trust.json',trust),('execution-policy.json',execution),
                        ('operator-policy.json',operator),('s3-endpoint-policy.json',endpoint)]:
        (out/name).write_text(json.dumps(policy,indent=2),encoding='utf-8')
    print('Created iam/rendered/*.json locally; apply through the console per assignment.')

if __name__=='__main__': main()
