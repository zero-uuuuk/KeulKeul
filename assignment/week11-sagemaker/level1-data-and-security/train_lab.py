"""Explicit, resumable SageMaker lab steps. No AWS work occurs on import.

Windows/macOS: use boto3 directly, not SageMaker Python SDK's Unix-oriented runtime.
"""
import argparse
import csv
import io
import json
import re
import time
import uuid
import sys
from datetime import date
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
sys.path.insert(0, str(DATA.parent))
STATE = ROOT / 'lab_state.json'
IMAGE = '366743142698.dkr.ecr.ap-northeast-2.amazonaws.com/sagemaker-xgboost:1.7-1'
INSTANCE = 'ml.m5.xlarge'

def load():
    cfg = json.loads((ROOT / 'config.json').read_text(encoding='utf-8-sig'))
    if cfg['region'] != 'ap-northeast-2' or not re.fullmatch(r'\d{12}', cfg['account_id']):
        raise ValueError('Set a 12-digit account ID and ap-northeast-2 in config.json')
    if not cfg['bucket'].startswith('keulkeul-week11-' + cfg['account_id'] + '-'):
        raise ValueError('Use the documented account-specific bucket name')
    session = boto3.Session(profile_name=cfg['profile'], region_name=cfg['region'])
    if session.client('sts').get_caller_identity()['Account'] != cfg['account_id']:
        raise ValueError('AWS credential account differs from config.json')
    return cfg, session


def save(st):
    temporary = STATE.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(st, indent=2), encoding='utf-8')
    temporary.replace(STATE)

def state(cfg, create=False):
    identity = dict(account_id=cfg['account_id'], region=cfg['region'], bucket=cfg['bucket'])
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding='utf-8'))
        if any(st.get(k) != v for k, v in identity.items()):
            raise ValueError('State belongs to a different account, region or bucket')
        for key in ['training']:
            if not re.fullmatch(r'keulkeul-w11-[a-z0-9-]+', st[key]):
                raise ValueError('Unexpected resource name in state')
        return st
    if not create:
        raise ValueError('No lab_state.json. Use console to inspect any resources created previously.')
    stem = 'keulkeul-w11-' + date.today().strftime('%m%d') + '-' + uuid.uuid4().hex[:8]
    st = dict(**identity, training=stem+'-train')
    save(st)
    return st

def optional(client, method, **kwargs):
    try:
        return getattr(client, method)(**kwargs)
    except ClientError as e:
        error = e.response['Error']
        msg = error.get('Message', '').lower()
        if error['Code'] in ['ValidationException', 'ResourceNotFound', 'ResourceNotFoundException'] and any(
                v in msg for v in ['could not find', 'does not exist', 'not found', 'cannot find']):
            return None
        raise

def preflight(cfg, session):
    location = session.client('s3').get_bucket_location(Bucket=cfg['bucket'])['LocationConstraint']
    if location != cfg['region']:
        raise ValueError('Bucket must be in Seoul')
    role = session.client('iam').get_role(RoleName='keulkeul-week11-sagemaker-role')['Role']
    if role['Arn'] != cfg['role_arn']:
        raise ValueError('Execution role ARN mismatch')
    print('Account, region, bucket and training role checked.')

def upload(cfg, session):
    s3 = session.client('s3')
    # Only these exact files are uploaded; test labels remain on the local PC.
    for name in ['prices.csv', 'metadata.json', 'train.csv', 'validation.csv']:
        key = 'week11/' + ('raw/' if name in ['prices.csv','metadata.json'] else 'input/') + name
        s3.upload_file(str(DATA/name), cfg['bucket'], key)
        print('s3://' + cfg['bucket'] + '/' + key)

def train(cfg, session):
    preflight(cfg, session)
    st = state(cfg, create=True)
    sm = session.client('sagemaker')
    job = optional(sm, 'describe_training_job', TrainingJobName=st['training'])
    if not job:
        sm.create_training_job(
            TrainingJobName=st['training'], RoleArn=cfg['role_arn'],
            AlgorithmSpecification={'TrainingImage':IMAGE, 'TrainingInputMode':'File'},
            HyperParameters={'objective':'reg:squarederror','eval_metric':'rmse','num_round':'80',
                             'max_depth':'3','eta':'0.05','subsample':'1','colsample_bytree':'1'},
            InputDataConfig=[{'ChannelName':channel,'ContentType':'text/csv',
                'DataSource':{'S3DataSource':{'S3DataType':'S3Prefix','S3Uri':
                 f"s3://{cfg['bucket']}/week11/input/{filename}.csv",'S3DataDistributionType':'FullyReplicated'}}}
                for channel,filename in [('train','train'),('validation','validation')]],
            OutputDataConfig={'S3OutputPath':f"s3://{cfg['bucket']}/week11/output/"},
            ResourceConfig={'InstanceType':INSTANCE,'InstanceCount':1,'VolumeSizeInGB':5},
            StoppingCondition={'MaxRuntimeInSeconds':600},
            Tags=[{'Key':'Project','Value':'keulkeul-week11'}])
    for _ in range(90):
        job = sm.describe_training_job(TrainingJobName=st['training'])
        print(job['TrainingJobStatus'], job.get('SecondaryStatus',''))
        if job['TrainingJobStatus'] == 'Completed':
            st['model_data'] = job['ModelArtifacts']['S3ModelArtifacts']
            save(st)
            handoff = dict(account_id=cfg['account_id'], region=cfg['region'],
                           bucket=cfg['bucket'], role_arn=cfg['role_arn'], profile=cfg['profile'],
                           training=st['training'], model_data=st['model_data'])
            out = ROOT / 'outputs'; out.mkdir(exist_ok=True)
            (out / 'training-result.json').write_text(json.dumps(handoff, indent=2), encoding='utf-8')
            print('Saved outputs/training-result.json')
            print('Model artifact:', st['model_data'])
            print('Final metrics:', job.get('FinalMetricDataList', []))
            return
        if job['TrainingJobStatus'] in ['Failed','Stopped']:
            raise RuntimeError(job.get('FailureReason',job['TrainingJobStatus']) + '; no automatic new job is launched')
        time.sleep(20)
    raise TimeoutError('Status wait ended. AWS job may continue: use status or cleanup --execute.')

def status(cfg, session):
    st = state(cfg)
    job = optional(session.client('sagemaker'), 'describe_training_job', TrainingJobName=st['training'])
    print('Training:', job['TrainingJobStatus'] if job else 'absent')
    if job and job['TrainingJobStatus'] == 'Completed':
        print('Model artifact:', job['ModelArtifacts']['S3ModelArtifacts'])

def cleanup(cfg, session, execute=False):
    st = state(cfg)
    print('Training job:', st['training'])
    if not execute:
        print('Preview only. Add --execute to stop this training job.')
        return
    sm = session.client('sagemaker')
    job = optional(sm, 'describe_training_job', TrainingJobName=st['training'])
    if job and job['TrainingJobStatus'] == 'InProgress':
        sm.stop_training_job(TrainingJobName=st['training'])
        print('Training stop requested; verify Stopped in console.')
    else:
        print('No running training job. S3 model files are retained for lab 2.')

def main():
    parser = argparse.ArgumentParser(description='Lab 1: upload and train. No customer VPC required.')
    parser.add_argument('command', choices=['preflight', 'upload', 'train', 'status', 'cleanup'])
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    cfg, session = load()
    if args.command == 'cleanup': cleanup(cfg, session, args.execute)
    else: globals()[args.command](cfg, session)

if __name__ == '__main__': main()
