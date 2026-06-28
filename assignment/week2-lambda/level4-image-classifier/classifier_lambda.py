"""역할: S3에 업로드된 이미지를 CNN 모델로 분류하고 결과 JSON을 다른 S3 버킷에 저장한다.

상세 과정:
  1. S3 객체 생성 이벤트에서 업로드 버킷과 객체 key를 읽는다.
  2. 이미지를 다운로드한 뒤 SqueezeNet ONNX 모델 입력 형식으로 전처리한다.
  3. 추론 결과를 고양이, 강아지, unknown 중 하나로 매핑해 결과 버킷에 저장한다.
"""

from __future__ import annotations

import io
import json
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote_plus

import boto3
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps


# ---------------------------------------------------------------------------
# 기본 설정 (모델 및 S3)
# ---------------------------------------------------------------------------

MODEL_PATH = os.getenv("MODEL_PATH", "/var/task/squeezenet1.1-7.onnx")
RESULT_BUCKET = os.environ["RESULT_BUCKET"]
MODEL_NAME = "squeezenet1.1-7"
IMAGE_SIZE = 224

s3_client = boto3.client("s3")
onnx_session: ort.InferenceSession | None = None


# ---------------------------------------------------------------------------
# ImageNet class 매핑
# ---------------------------------------------------------------------------

CAT_CLASS_NAMES = {
    281: "tabby",
    282: "tiger_cat",
    283: "Persian_cat",
    284: "Siamese_cat",
    285: "Egyptian_cat",
}
DOG_CLASS_IDS = set(range(151, 269))


# ---------------------------------------------------------------------------
# 모델 추론
# ---------------------------------------------------------------------------

def get_onnx_session() -> ort.InferenceSession:
    """Lambda 실행 환경 안에서 ONNX 세션을 한 번만 생성해 재사용한다."""

    # 전역 세션을 재사용하면 같은 실행 환경의 두 번째 호출부터 cold start 비용을 줄일 수 있다.
    global onnx_session
    if onnx_session is None:
        onnx_session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])

    return onnx_session


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """S3에서 읽은 이미지 바이트를 SqueezeNet 입력 텐서로 변환한다."""

    # ImageNet 계열 모델의 일반적인 전처리인 RGB 변환, 224x224 중앙 crop, 정규화를 적용한다.
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = ImageOps.fit(image, (IMAGE_SIZE, IMAGE_SIZE), method=Image.Resampling.BILINEAR)
    image_array = np.asarray(image).astype(np.float32) / 255.0

    # 채널별 평균과 표준편차로 정규화한 뒤 NCHW 형태로 차원을 바꾼다.
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    normalized = (image_array - mean) / std
    channel_first = np.transpose(normalized, (2, 0, 1))

    return np.expand_dims(channel_first, axis=0).astype(np.float32)


def softmax(values: np.ndarray) -> np.ndarray:
    """모델 출력 logit을 확률처럼 비교할 수 있는 softmax 값으로 변환한다."""

    # overflow를 피하기 위해 최댓값을 뺀 뒤 지수 함수를 적용한다.
    shifted = values - np.max(values)
    exp_values = np.exp(shifted)
    return exp_values / np.sum(exp_values)


def classify_image(image_bytes: bytes) -> dict[str, Any]:
    """이미지를 SqueezeNet으로 분류하고 고양이/강아지 여부를 반환한다."""

    # ONNX 모델의 첫 번째 입력 이름을 사용해 전처리된 텐서를 전달한다.
    session = get_onnx_session()
    input_name = session.get_inputs()[0].name
    model_outputs = session.run(None, {input_name: preprocess_image(image_bytes)})

    # SqueezeNet 출력은 1000개 ImageNet class 점수이며, 가장 높은 class를 대표 예측으로 사용한다.
    logits = np.squeeze(model_outputs[0])
    probabilities = softmax(logits)
    top_class_id = int(np.argmax(probabilities))
    confidence = float(probabilities[top_class_id])

    # ImageNet class id를 이번 과제의 고양이/강아지/unknown 결과로 축약한다.
    if top_class_id in CAT_CLASS_NAMES:
        prediction = "cat"
        top_class_name = CAT_CLASS_NAMES[top_class_id]
    elif top_class_id in DOG_CLASS_IDS:
        prediction = "dog"
        top_class_name = f"dog_class_{top_class_id}"
    else:
        prediction = "unknown"
        top_class_name = f"imagenet_class_{top_class_id}"

    return {
        "prediction": prediction,
        "confidence": round(confidence, 6),
        "top_class_id": top_class_id,
        "top_class_name": top_class_name,
        "model": MODEL_NAME,
    }


# ---------------------------------------------------------------------------
# S3 입출력
# ---------------------------------------------------------------------------

def read_s3_object(bucket: str, key: str) -> bytes:
    """S3 객체를 바이트로 읽어 반환한다."""

    # 이미지는 메모리에서 바로 전처리할 수 있을 정도로 작은 파일만 실습 대상으로 한다.
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def write_result(source_bucket: str, source_key: str, result: dict[str, Any], request_id: str) -> str:
    """분류 결과를 result bucket의 JSON 파일과 latest.json에 저장한다."""

    # 원본 key를 보존해 API에서 같은 key로 결과를 조회할 수 있게 한다.
    result_key = f"results/{source_key}.json"
    result_body = {
        "source_bucket": source_bucket,
        "source_key": source_key,
        "result_key": result_key,
        "request_id": request_id,
        "created_at": datetime.now(UTC).isoformat(),
        **result,
    }
    result_bytes = json.dumps(result_body, ensure_ascii=False, indent=2).encode("utf-8")

    # 개별 결과와 최신 결과를 함께 저장해 API 조회 실습을 단순하게 만든다.
    s3_client.put_object(
        Bucket=RESULT_BUCKET,
        Key=result_key,
        Body=result_bytes,
        ContentType="application/json; charset=utf-8",
    )
    s3_client.put_object(
        Bucket=RESULT_BUCKET,
        Key="latest.json",
        Body=result_bytes,
        ContentType="application/json; charset=utf-8",
    )

    return result_key


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """S3 업로드 이벤트를 받아 이미지 분류 결과를 S3에 저장한다."""

    # S3는 여러 객체 이벤트를 한 번에 전달할 수 있으므로 Records 전체를 순회한다.
    processed_records: list[dict[str, Any]] = []
    request_id = getattr(context, "aws_request_id", "")

    for record in event.get("Records", []):
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name", "")
        key = unquote_plus(s3_info.get("object", {}).get("key", ""))

        # 업로드된 이미지를 읽고, 모델 추론 결과를 result bucket에 JSON으로 저장한다.
        image_bytes = read_s3_object(bucket, key)
        classification = classify_image(image_bytes)
        result_key = write_result(bucket, key, classification, request_id)

        # CloudWatch Logs에서 원본과 결과 위치를 바로 확인할 수 있게 남긴다.
        print(
            f"이미지 분류 완료: source=s3://{bucket}/{key}, "
            f"prediction={classification['prediction']}, result=s3://{RESULT_BUCKET}/{result_key}"
        )
        processed_records.append({"source_bucket": bucket, "source_key": key, "result_key": result_key})

    return {
        "processed_count": len(processed_records),
        "records": processed_records,
    }
