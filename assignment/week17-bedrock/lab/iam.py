import json
from .config import ROOT


def resource_names(c):
    return {
        "bucket_arn": f"arn:aws:s3:::{c['bucket']}",
        "vector_bucket_arn": f"arn:aws:s3vectors:{c['region']}:{c['account_id']}:bucket/{c['vector_bucket']}",
        "index_arn": f"arn:aws:s3vectors:{c['region']}:{c['account_id']}:bucket/{c['vector_bucket']}/index/{c['vector_index']}",
        "role_arn": f"arn:aws:iam::{c['account_id']}:role/{c['service_role']}",
        "kb_arn": f"arn:aws:bedrock:{c['region']}:{c['account_id']}:knowledge-base/{c.get('knowledge_base_id') or '*'}",
        "embedding_arn": f"arn:aws:bedrock:{c['region']}::foundation-model/amazon.titan-embed-text-v2:0",
    }


def policies(c):
    n = resource_names(c)
    def allow(actions, resources, condition=None):
        s = {"Effect": "Allow", "Action": actions, "Resource": resources}
        if condition:
            s["Condition"] = condition
        return s
    def policy(*statements):
        return {"Version": "2012-10-17", "Statement": list(statements)}
    trust = policy({"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"}, "Action": "sts:AssumeRole",
                    "Condition": {"StringEquals": {"aws:SourceAccount": c["account_id"]},
                                  "ArnLike": {"aws:SourceArn": n["kb_arn"]}}})
    access = policy(
        allow("s3:ListBucket", n["bucket_arn"]),
        allow("s3:GetObject", n["bucket_arn"] + "/docs/*"),
        allow("bedrock:InvokeModel", n["embedding_arn"]),
        allow(["s3vectors:GetIndex", "s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors", "s3vectors:QueryVectors"], n["index_arn"]))
    storage = policy(
        allow(["s3:ListAllMyBuckets", "s3:GetAccountPublicAccessBlock", "s3vectors:ListVectorBuckets"], "*"),
        allow(["s3:CreateBucket", "s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketPublicAccessBlock", "s3:PutBucketPublicAccessBlock", "s3:DeleteBucket"], n["bucket_arn"]),
        allow(["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], n["bucket_arn"] + "/docs/*"),
        allow(["s3vectors:CreateVectorBucket", "s3vectors:GetVectorBucket", "s3vectors:ListIndexes", "s3vectors:DeleteVectorBucket"], n["vector_bucket_arn"]),
        allow(["s3vectors:CreateIndex", "s3vectors:GetIndex", "s3vectors:DeleteIndex"], n["index_arn"]))
    role = policy(
        allow("iam:ListRoles", "*"),
        allow(["iam:CreateRole", "iam:GetRole", "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:UpdateAssumeRolePolicy", "iam:ListRolePolicies", "iam:DeleteRolePolicy", "iam:DeleteRole"], n["role_arn"]),
        allow("iam:PassRole", n["role_arn"], {"StringEquals": {"iam:PassedToService": "bedrock.amazonaws.com"}}))
    kb = policy(
        allow("bedrock:CreateKnowledgeBase", "*", {"StringEquals": {"aws:RequestedRegion": c["region"]}}),
        allow(["bedrock:ListKnowledgeBases", "bedrock:ListFoundationModels", "bedrock:ListInferenceProfiles"], "*", {"StringEquals": {"aws:RequestedRegion": c["region"]}}),
        allow(["bedrock:GetKnowledgeBase", "bedrock:DeleteKnowledgeBase", "bedrock:CreateDataSource", "bedrock:ListDataSources", "bedrock:GetDataSource", "bedrock:DeleteDataSource", "bedrock:StartIngestionJob", "bedrock:GetIngestionJob", "bedrock:ListIngestionJobs"], n["kb_arn"]))
    runtime = policy(
        allow("bedrock:Retrieve", n["kb_arn"]),
        allow("bedrock:InvokeModel", [f"arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0", f"arn:aws:bedrock:{c['region']}:{c['account_id']}:inference-profile/apac.amazon.nova-lite-v1:0"]),
        allow("bedrock:GetInferenceProfile", f"arn:aws:bedrock:{c['region']}:{c['account_id']}:inference-profile/apac.amazon.nova-lite-v1:0"))
    return {"01-storage-setup.json": storage, "02-role-setup.json": role, "03-kb-setup.json": kb,
            "04-app-runtime.json": runtime, "kb-service-trust.json": trust, "kb-service-access.json": access}


def render(c):
    target = ROOT / "iam/generated"
    target.mkdir(parents=True, exist_ok=True)
    for name, policy in policies(c).items():
        compact = len(json.dumps(policy, separators=(",", ":")))
        if compact > 6144:
            raise ValueError("고객 관리형 정책이 6144자를 초과합니다: " + name)
        (target / name).write_text(json.dumps(policy, indent=2), encoding="utf-8")
        print(name, ":", compact, "characters (whitespace excluded)")
    print("01~04는 고객 관리형 정책으로 생성해 실습 사용자에 연결하세요. kb-service-*는 서비스 역할 전용입니다.")
