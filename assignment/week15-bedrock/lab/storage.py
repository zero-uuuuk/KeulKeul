import json
import time
from .config import ROOT
from .iam import resource_names, policies


def plan(c):
    return {"account_id": c["account_id"], "region": c["region"], "s3_bucket": c["bucket"],
            "source_prefix": "docs/", "vector_bucket": c["vector_bucket"], "vector_index": c["vector_index"],
            "embedding": "amazon.titan-embed-text-v2:0", "dimensions": 1024,
            "knowledge_base_name": "keulkeul-bedrock-" + c["suffix"], **resource_names(c)}


def prepare(c, session):
    """Create dedicated storage and role only; the learner creates the KB in console."""
    path = ROOT / ".local/storage-state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if state and (state["account_id"] != c["account_id"] or state["suffix"] != c["suffix"]):
        raise ValueError("이미 다른 설정으로 준비한 상태 파일이 있습니다. 기존 자원을 먼저 확인하세요.")
    if not state:
        state = {"account_id": c["account_id"], "suffix": c["suffix"], "created": {}}
    path.parent.mkdir(exist_ok=True)
    def save():
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    save()
    done = state["created"]
    s3, vectors, iam = (session.client(name) for name in ("s3", "s3vectors", "iam"))
    if not done.get("s3"):
        s3.create_bucket(Bucket=c["bucket"], CreateBucketConfiguration={"LocationConstraint": c["region"]})
        done["s3"] = c["bucket"]; save()
        print("원본 S3 생성 완료")
    s3.put_public_access_block(Bucket=c["bucket"], ExpectedBucketOwner=c["account_id"],
        PublicAccessBlockConfiguration={k: True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")})
    if not done.get("vector_bucket"):
        vectors.create_vector_bucket(vectorBucketName=c["vector_bucket"])
        done["vector_bucket"] = c["vector_bucket"]; save()
        print("S3 벡터 버킷 생성 완료")
    if not done.get("index"):
        vectors.create_index(vectorBucketName=c["vector_bucket"], indexName=c["vector_index"], dataType="float32",
            dimension=1024, distanceMetric="cosine",
            metadataConfiguration={"nonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]})
        done["index"] = c["vector_index"]; save()
        print("1024차원 벡터 인덱스 생성 완료")
    if not done.get("role"):
        iam.create_role(RoleName=c["service_role"], AssumeRolePolicyDocument=json.dumps(policies(c)["kb-service-trust.json"]),
                        Description="KEULKEUL Bedrock foundations lab service role")
        done["role"] = c["service_role"]; save()
    iam.put_role_policy(RoleName=c["service_role"], PolicyName="KnowledgeBaseDataAccess",
                        PolicyDocument=json.dumps(policies(c)["kb-service-access.json"]))
    print("준비 완료. 이제 콘솔에서 KB를 직접 연결하세요. IAM 전파에 시간이 걸릴 수 있습니다.")


def check(c, agent, s3):
    n = resource_names(c)
    kb = agent.get_knowledge_base(knowledgeBaseId=c["knowledge_base_id"])["knowledgeBase"]
    if kb["status"] != "ACTIVE":
        raise ValueError("Knowledge Base가 ACTIVE 상태가 아닙니다: " + kb["status"])
    if kb["knowledgeBaseConfiguration"]["type"] != "VECTOR":
        raise ValueError("이 실습은 별도 Managed KB가 아닌 VECTOR KB를 사용합니다.")
    vector_config = kb["knowledgeBaseConfiguration"]["vectorKnowledgeBaseConfiguration"]
    if vector_config["embeddingModelArn"] != n["embedding_arn"]:
        raise ValueError("KB 임베딩 모델이 공통 실습 설정과 다릅니다.")
    dimensions = vector_config.get("embeddingModelConfiguration", {}).get("bedrockEmbeddingModelConfiguration", {}).get("dimensions", 1024)
    if dimensions != 1024:
        raise ValueError("KB 임베딩 차원은 1024여야 합니다.")
    store = kb["storageConfiguration"]
    if store.get("type") != "S3_VECTORS":
        raise ValueError("이 실습에서 준비한 S3 Vectors 연결을 사용하세요.")
    v = store["s3VectorsConfiguration"]
    if v.get("indexArn") != n["index_arn"] and not (v.get("vectorBucketArn") == n["vector_bucket_arn"] and v.get("indexName") == c["vector_index"]):
        raise ValueError("KB의 벡터 인덱스가 실습용 설정과 다릅니다.")
    if kb["roleArn"] != n["role_arn"]:
        raise ValueError("KB 서비스 역할이 제공된 실습 역할과 다릅니다.")
    source = agent.get_data_source(knowledgeBaseId=c["knowledge_base_id"], dataSourceId=c["data_source_id"])["dataSource"]
    if source["status"] != "AVAILABLE":
        raise ValueError("데이터 소스가 AVAILABLE 상태가 아닙니다: " + source["status"])
    s = source["dataSourceConfiguration"]["s3Configuration"]
    if s["bucketArn"] != n["bucket_arn"] or s.get("inclusionPrefixes") != ["docs/"]:
        raise ValueError("S3 데이터 소스를 원본 버킷의 docs/로 연결하세요.")
    s3.head_bucket(Bucket=c["bucket"], ExpectedBucketOwner=c["account_id"])
    return {"kb_status": kb["status"], "data_source_status": source["status"], "bucket": c["bucket"]}


def sync(c, agent, timeout=240):
    job = agent.start_ingestion_job(knowledgeBaseId=c["knowledge_base_id"], dataSourceId=c["data_source_id"])["ingestionJob"]
    deadline = time.monotonic() + timeout
    while job["status"] not in {"COMPLETE", "FAILED", "STOPPED"}:
        if time.monotonic() >= deadline:
            raise TimeoutError("4분이 지났습니다. 작업을 취소하지 않았으니 콘솔에서 기존 작업 상태를 확인하세요.")
        print("Sync 상태:", job["status"])
        time.sleep(5)
        job = agent.get_ingestion_job(knowledgeBaseId=c["knowledge_base_id"], dataSourceId=c["data_source_id"],
                                      ingestionJobId=job["ingestionJobId"])["ingestionJob"]
    if job["status"] != "COMPLETE" or job.get("statistics", {}).get("numberOfDocumentsFailed", 0):
        raise ValueError("동기화 실패 문서가 있습니다: " + json.dumps(job, default=str))
    return job
