"""역할: Hugging Face 로컬 embedding 모델과 S3 Vectors를 연결해 RAG 흐름을 실행한다.

상세 과정:
  1. 실습용 문서를 sentence-transformers 모델로 벡터화해 S3 vector index에 저장한다.
  2. 사용자 질문을 같은 embedding 모델로 벡터화한 뒤 S3 Vectors에서 유사 문서를 조회한다.
  3. 조회된 문맥을 Hugging Face 로컬 LLM에 전달해 답변을 생성한다.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import boto3
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer


# ---------------------------------------------------------------------------
# 실습 설정
# ---------------------------------------------------------------------------

AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
VECTOR_BUCKET_NAME = os.getenv("S3_VECTOR_BUCKET", "")
VECTOR_INDEX_NAME = os.getenv("S3_VECTOR_INDEX", "keulkeul-rag")
EMBED_MODEL_NAME = os.getenv(
    "HF_EMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
# 한국어를 포함한 멀티링구얼 성능이 좋으면서 로컬에서 돌릴 수 있는 소형 instruction 모델.
LLM_MODEL_NAME = os.getenv("HF_LLM_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
DOCUMENT_PATH = Path(__file__).with_name("rag_documents.json")


# ---------------------------------------------------------------------------
# 실습용 문서 로딩
# ---------------------------------------------------------------------------

def load_documents() -> list[dict[str, str]]:
    """별도 JSON 파일에 저장된 실습 문서를 읽어온다."""

    # 문서 내용을 코드와 분리해 RAG에서 색인 대상 데이터가 무엇인지 명확히 보여준다.
    with DOCUMENT_PATH.open(encoding="utf-8") as document_file:
        documents = json.load(document_file)

    # S3 Vectors에 넣을 최소 필드가 빠졌는지 실행 초기에 확인한다.
    required_keys = {"key", "category", "text"}
    for document in documents:
        missing_keys = required_keys - document.keys()
        if missing_keys:
            raise RuntimeError(f"문서에 필요한 필드가 없습니다: {sorted(missing_keys)}")

    return documents


# ---------------------------------------------------------------------------
# 로컬 embedding 생성
# ---------------------------------------------------------------------------

def load_embed_model() -> SentenceTransformer:
    """Hugging Face sentence-transformers 모델을 로컬 프로세스로 불러온다."""

    # 첫 실행 때 모델 파일을 내려받고, 이후에는 로컬 캐시를 재사용한다.
    print(f"[모델 로딩] embedding: {EMBED_MODEL_NAME}")
    model = SentenceTransformer(EMBED_MODEL_NAME)
    print("[모델 로딩 완료] embedding")
    return model


def load_llm() -> tuple[Any, Any]:
    """Hugging Face causal LLM과 tokenizer를 로컬 프로세스로 불러온다."""

    # 한국어 답변 품질을 위해 instruction-tuned causal 모델을 직접 로드한다.
    print(f"[모델 로딩] LLM: {LLM_MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(LLM_MODEL_NAME)
    print("[모델 로딩 완료] LLM")
    return tokenizer, model


def embed_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    """여러 텍스트를 같은 embedding 공간의 float32 vector로 변환한다."""

    # normalize_embeddings=True는 cosine 검색에서 길이 차이 영향을 줄인다.
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    # boto3 JSON 직렬화가 가능한 Python float list로 변환한다.
    return embeddings.astype("float32").tolist()


# ---------------------------------------------------------------------------
# S3 Vectors 호출
# ---------------------------------------------------------------------------

def create_s3vectors_client() -> Any:
    """S3 Vectors 전용 boto3 client를 생성한다."""

    # S3 Vectors는 일반 s3 client가 아니라 s3vectors namespace를 사용한다.
    if not VECTOR_BUCKET_NAME:
        raise RuntimeError("S3_VECTOR_BUCKET 환경 변수를 먼저 설정한다.")

    return boto3.client("s3vectors", region_name=AWS_REGION)


def ingest_documents() -> None:
    """실습 문서를 embedding으로 변환한 뒤 S3 vector index에 저장한다."""

    # 문서 본문만 모아 embedding 모델 입력으로 넘긴다.
    print("[1/4] S3 Vectors client 생성")
    client = create_s3vectors_client()
    print("[2/4] embedding 모델 로딩")
    model = load_embed_model()
    print("[3/4] 원본 문서 로딩 및 embedding 생성")
    documents = load_documents()
    texts = [document["text"] for document in documents]
    embeddings = embed_texts(model, texts)

    # S3 Vectors의 각 vector에는 key, float32 vector, metadata를 함께 저장한다.
    vectors = []
    for document, embedding in zip(documents, embeddings, strict=True):
        vectors.append(
            {
                "key": document["key"],
                "data": {"float32": embedding},
                "metadata": {
                    "category": document["category"],
                    "source_text": document["text"],
                },
            }
        )

    # 작은 실습 데이터는 한 번에 저장하지만, 실제 데이터는 batch 단위로 나누는 것이 좋다.
    print("[4/4] S3 Vectors에 저장")
    client.put_vectors(
        vectorBucketName=VECTOR_BUCKET_NAME,
        indexName=VECTOR_INDEX_NAME,
        vectors=vectors,
    )
    print(f"{len(vectors)}개 문서를 S3 Vectors에 저장했다.")


def search_documents(question: str, top_k: int) -> list[dict[str, Any]]:
    """질문과 의미가 가까운 문서를 S3 vector index에서 조회한다."""

    # 질문도 저장할 때와 같은 embedding 모델로 변환해야 vector 공간이 일관된다.
    print("[1/4] S3 Vectors client 생성")
    client = create_s3vectors_client()
    print("[2/4] embedding 모델 로딩")
    model = load_embed_model()
    print("[3/4] 질문 embedding 생성")
    question_embedding = embed_texts(model, [question])[0]

    # QueryVectors는 유사도 상위 결과와 metadata를 함께 반환할 수 있다.
    print("[4/4] S3 Vectors 유사 문서 검색")
    response = client.query_vectors(
        vectorBucketName=VECTOR_BUCKET_NAME,
        indexName=VECTOR_INDEX_NAME,
        queryVector={"float32": question_embedding},
        filter={"category": "s3-vectors"},
        topK=top_k,
        returnDistance=True,
        returnMetadata=True,
    )

    return list(response.get("vectors", []))


def answer_with_local_llm(question: str, top_k: int) -> None:
    """검색 결과를 Hugging Face 로컬 LLM context로 전달해 답변을 생성한다."""

    # S3 Vectors에서 검색한 source_text만 LLM의 근거 문맥으로 사용한다.
    results = search_documents(question, top_k)
    context = "\n".join(
        f"- {vector.get('metadata', {}).get('source_text', '')}"
        for vector in results
    )

    # instruction 모델이 근거 밖 내용을 지어내지 않도록 답변 범위를 한국어로 명시한다.
    messages = [
        {
            "role": "system",
            "content": "너는 주어진 context만 근거로 한국어로 답하는 도우미다. "
            "context에 없는 내용은 추측하지 말고 모른다고 답한다.",
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\n질문: {question}",
        },
    ]

    # causal 모델은 chat template로 대화를 프롬프트 문자열로 변환한 뒤 이어서 생성한다.
    tokenizer, model = load_llm()
    print("[LLM 답변 생성]")
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
    outputs = model.generate(**inputs, max_new_tokens=256, do_sample=False)

    # 입력 프롬프트 뒤에 새로 생성된 token만 잘라 답변으로 디코딩한다.
    generated_tokens = outputs[0][inputs["input_ids"].shape[-1] :]
    answer = tokenizer.decode(generated_tokens, skip_special_tokens=True)

    print("[검색 문맥]")
    print(context)
    print("\n[LLM 답변]")
    print(answer)


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """터미널에서 실행할 하위 명령과 질문 인자를 파싱한다."""

    # ingest는 저장 단계, ask는 검색과 LLM 답변 단계를 실행한다.
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest")

    # 질문 명령은 검색 결과 개수를 조정할 수 있게 top-k 옵션을 제공한다.
    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--top-k", type=int, default=2)

    return parser.parse_args()


def main() -> None:
    """CLI 명령에 따라 문서 저장 또는 질문 검색을 실행한다."""

    # 하위 명령에 따라 전체 RAG 흐름 중 필요한 단계만 실행한다.
    args = parse_args()
    if args.command == "ingest":
        ingest_documents()
        return

    if args.command == "ask":
        answer_with_local_llm(args.question, args.top_k)
        return


if __name__ == "__main__":
    main()
