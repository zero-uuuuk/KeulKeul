import boto3
from botocore.config import Config


def session_for(config):
    session = boto3.Session(profile_name=config.get("profile") or None, region_name=config["region"])
    identity = session.client("sts", config=Config(connect_timeout=10, read_timeout=20)).get_caller_identity()
    if identity["Account"] != config["account_id"]:
        raise ValueError("로그인 계정과 config.json의 account_id가 다릅니다. AWS 호출을 중단했습니다.")
    if identity["Arn"].endswith(":root"):
        raise ValueError("이 실습은 IAM 사용자/역할로 로그인해야 합니다. root 세션을 바꾸세요.")
    return session


def client(session, service):
    return session.client(service, config=Config(connect_timeout=10, read_timeout=120,
                                                retries={"max_attempts": 2, "mode": "standard"}))
