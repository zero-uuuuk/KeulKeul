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
DATA = ROOT.parent / 'level1-data-and-security' / 'data'
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
        for key in ['model', 'endpoint_config', 'endpoint']:
            if not re.fullmatch(r'keulkeul-w11-[a-z0-9-]+', st[key]):
                raise ValueError('Unexpected resource name in state')
        return st
    if not create:
        raise ValueError('No lab_state.json. Use console to inspect any resources created previously.')
    stem = 'keulkeul-w11-' + date.today().strftime('%m%d') + '-' + uuid.uuid4().hex[:8]
    st = dict(**identity, model_data=cfg['model_data'], model=stem+'-model',
              endpoint_config=stem+'-config', endpoint=stem+'-endpoint')
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
    s3 = session.client('s3')
    location = s3.get_bucket_location(Bucket=cfg['bucket'])['LocationConstraint']
    if location != cfg['region']:
        raise ValueError('Bucket must be in Seoul')
    role = session.client('iam').get_role(RoleName='keulkeul-week11-sagemaker-role')['Role']
    if role['Arn'] != cfg['role_arn']:
        raise ValueError('Execution role ARN mismatch')
    ec2 = session.client('ec2')
    if len(set(cfg['subnet_ids'])) != 2:
        raise ValueError('Set two different subnet IDs in different availability zones')
    subnets = ec2.describe_subnets(SubnetIds=cfg['subnet_ids'])['Subnets']
    sg = ec2.describe_security_groups(GroupIds=[cfg['security_group_id']])['SecurityGroups'][0]
    if len({s['AvailabilityZone'] for s in subnets}) != 2:
        raise ValueError('Hosting requires subnets in two different availability zones')
    if any(s['VpcId'] != sg['VpcId'] or s['AvailableIpAddressCount'] < 4 for s in subnets):
        raise ValueError('Subnet/SG VPC mismatch or fewer than 4 available addresses')
    eps = ec2.describe_vpc_endpoints(Filters=[{'Name':'vpc-id','Values':[sg['VpcId']]},
        {'Name':'service-name','Values':['com.amazonaws.ap-northeast-2.s3']}])['VpcEndpoints']
    for subnet in subnets:
        routes = ec2.describe_route_tables(Filters=[{'Name':'association.subnet-id','Values':[subnet['SubnetId']]}])['RouteTables']
        if not routes:
            routes = ec2.describe_route_tables(Filters=[{'Name':'vpc-id','Values':[sg['VpcId']]},
                                                       {'Name':'association.main','Values':['true']}])['RouteTables']
        table = routes[0]
        if any(r.get('DestinationCidrBlock') == '0.0.0.0/0' for r in table['Routes']):
            raise ValueError('Use the lab private subnets without an Internet/NAT default route')
        if not any(e['VpcEndpointType']=='Gateway' and e['State']=='available'
                   and table['RouteTableId'] in e.get('RouteTableIds',[]) for e in eps):
            raise ValueError('Attach an available S3 Gateway endpoint to both subnet route tables')
    print('Account, region, bucket, role and VPC route checked.')
    print('Manually confirm hosting allowance, quota and SG outbound TCP 443 to S3 prefix list.')
    print('Hosting instance:', INSTANCE, '| container:', IMAGE)

def status(cfg, session):
    if not STATE.exists():
        print('Deployment not started; no local deployment state.')
        return
    st = state(cfg)
    ep = optional(session.client('sagemaker'), 'describe_endpoint', EndpointName=st['endpoint'])
    print('Endpoint:', ep['EndpointStatus'] if ep else 'absent')
    print(json.dumps(st, indent=2))

def cleanup(cfg, session, execute=False):
    st = state(cfg)
    print('Scope: state-recorded endpoint, endpoint config and model only.')
    print(json.dumps(st, indent=2))
    if not execute:
        print('Preview only. Add --execute to stop/delete these resources.')
        return
    sm = session.client('sagemaker')
    ep = optional(sm,'describe_endpoint',EndpointName=st['endpoint'])
    if ep:
        if ep['EndpointStatus'] != 'Deleting': sm.delete_endpoint(EndpointName=st['endpoint'])
        sm.get_waiter('endpoint_deleted').wait(EndpointName=st['endpoint'],
                                              WaiterConfig={'Delay':20,'MaxAttempts':90})
    if optional(sm,'describe_endpoint_config',EndpointConfigName=st['endpoint_config']):
        sm.delete_endpoint_config(EndpointConfigName=st['endpoint_config'])
    if optional(sm,'describe_model',ModelName=st['model']):
        sm.delete_model(ModelName=st['model'])
    print('Endpoint/config/model removed. S3, logs, VPC and IAM need manual cleanup per assignment.')

def predict(runtime, endpoint, frame, features):
    import numpy as np
    values=[]
    for start in range(0,len(frame),100):
        part=frame.iloc[start:start+100]
        payload=part[features].to_csv(index=False,header=False).encode('utf-8')
        res=runtime.invoke_endpoint(EndpointName=endpoint, ContentType='text/csv',Accept='text/csv',Body=payload)
        vals=[float(v) for row in csv.reader(io.StringIO(res['Body'].read().decode())) for v in row if v.strip()]
        if len(vals)!=len(part) or not np.isfinite(vals).all():
            raise ValueError('Unexpected inference response shape or non-finite value')
        values.extend(vals)
    return np.asarray(values)

def demo(cfg, session):
    import pandas as pd
    from local_model import FEATURES, compare
    preflight(cfg, session)
    artifact = cfg['model_data']
    prefix = f"s3://{cfg['bucket']}/week11/output/"
    if not artifact.startswith(prefix) or not artifact.endswith('/model.tar.gz'):
        raise ValueError('Use the lab 1 model.tar.gz in this bucket')
    key = artifact[len(f"s3://{cfg['bucket']}/"):]
    session.client('s3').head_object(Bucket=cfg['bucket'], Key=key)
    st=state(cfg, create=True)
    if st.get('model_data', artifact) != artifact:
        raise ValueError('State refers to another model; finish its cleanup first.')
    sm=session.client('sagemaker')
    try:
        if not optional(sm,'describe_model',ModelName=st['model']):
            sm.create_model(ModelName=st['model'],ExecutionRoleArn=cfg['role_arn'],
                PrimaryContainer={'Image':IMAGE,'ModelDataUrl':artifact},
                VpcConfig={'Subnets':cfg['subnet_ids'],'SecurityGroupIds':[cfg['security_group_id']]})
        if not optional(sm,'describe_endpoint_config',EndpointConfigName=st['endpoint_config']):
            sm.create_endpoint_config(EndpointConfigName=st['endpoint_config'],ProductionVariants=[
                {'VariantName':'AllTraffic','ModelName':st['model'],'InitialInstanceCount':1,
                 'InstanceType':INSTANCE,'InitialVariantWeight':1.0}])
        if not optional(sm,'describe_endpoint',EndpointName=st['endpoint']):
            sm.create_endpoint(EndpointName=st['endpoint'],EndpointConfigName=st['endpoint_config'])
        print('Endpoint creating:', st['endpoint'])
        sm.get_waiter('endpoint_in_service').wait(EndpointName=st['endpoint'],WaiterConfig={'Delay':20,'MaxAttempts':90})
        print('InService; predicting test rows and twelve latest rows, then deleting endpoint.')
        runtime=session.client('sagemaker-runtime',config=Config(read_timeout=70,retries={'max_attempts':3}))
        data=pd.read_csv(DATA/'examples.csv')
        test=data[data.split=='test'].copy()
        pred=predict(runtime,st['endpoint'],test,FEATURES)
        out=ROOT/'outputs'; out.mkdir(exist_ok=True)
        metrics=compare(test,pred)
        metrics.to_csv(out/'aws_metrics.csv',index=False)
        test['predicted_return']=pred
        test['predicted_close']=test.close*(1+pred)
        test.to_csv(out/'aws_predictions.csv',index=False)
        latest=pd.read_csv(DATA/'latest.csv')
        latest['predicted_day']=latest.day+1
        latest['predicted_close']=latest.close*(1+predict(runtime,st['endpoint'],latest,FEATURES))
        latest[['ticker','company','day','close','predicted_day','predicted_close']].to_csv(
            out/'aws_latest.csv',index=False,encoding='utf-8-sig')
        print(metrics.to_string(index=False))
        print('Results saved under outputs/')
    finally:
        # Runs on ordinary errors and Ctrl+C; cannot protect against power/network loss.
        cleanup(cfg,session,execute=True)

def prepare():
    # Local files only. Does not call AWS or create billable resources.
    source = ROOT.parent / 'level1-data-and-security' / 'outputs' / 'training-result.json'
    result = json.loads(source.read_text(encoding='utf-8-sig'))
    path = ROOT / 'config.json'
    if path.exists():
        cfg = json.loads(path.read_text(encoding='utf-8-sig'))
        for key in ['account_id', 'region', 'bucket', 'role_arn']:
            if cfg.get(key) != result[key]:
                raise ValueError('Existing deployment config differs from lab 1. No file overwritten.')
        if cfg.get('model_data') not in [None, result['model_data']]:
            raise ValueError('Existing config uses another model. No file overwritten.')
        cfg['model_data'] = result['model_data']
    else:
        cfg = {key: result[key] for key in ['account_id', 'region', 'bucket', 'role_arn', 'profile', 'model_data']}
        cfg.update(subnet_ids=['subnet-REPLACE_A','subnet-REPLACE_B'], security_group_id='sg-REPLACE')
    path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    # The renderer lives in this lab; invoking it only writes IAM JSON files.
    import subprocess
    subprocess.run([sys.executable, str(ROOT/'iam'/'render_policies.py'),
                    '--account-id', result['account_id'], '--bucket', result['bucket']], check=True)
    print('Deployment config and IAM JSON prepared locally. Set VPC IDs and attach policies per lab 2.')

def main():
    parser=argparse.ArgumentParser(description='Lab 2: prepare deployment environment and serve the lab 1 model.')
    parser.add_argument('command', choices=['prepare','preflight','status','demo','cleanup'])
    parser.add_argument('--execute', action='store_true')
    args=parser.parse_args()
    if args.command == 'prepare':
        prepare()
        return
    cfg, session = load()
    if args.command == 'cleanup': cleanup(cfg, session, args.execute)
    else: globals()[args.command](cfg, session)

if __name__=='__main__':
    main()
