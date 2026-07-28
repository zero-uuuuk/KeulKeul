"""역할: S3에 저장된 ONNX 모델을 로드해 테스트 추론 결과를 반환한다.

상세 과정:
  1. API Lambda가 전달한 modelBucket, modelId, artifactKey, imageKey를 읽는다.
  2. S3의 model.onnx 파일을 Lambda /tmp 경로로 내려받고 ONNX Runtime session을 만든다.
  3. S3의 테스트 이미지를 ResNet 입력 tensor로 전처리한 뒤 ImageNet category, confidence, latency 값을 반환한다.
"""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any

import boto3
import numpy as np
import onnxruntime as ort
from PIL import Image


# ---------------------------------------------------------------------------
# AWS 클라이언트 및 로컬 캐시
# ---------------------------------------------------------------------------
s3_client = boto3.client("s3")
session_cache: dict[str, ort.InferenceSession] = {}
imagenet_categories = Path(__file__).with_name("imagenet_classes.txt").read_text().splitlines()


# ---------------------------------------------------------------------------
# 모델 로드 및 추론 유틸리티
# ---------------------------------------------------------------------------
def load_session(model_bucket: str, artifact_key: str) -> ort.InferenceSession:
    """S3 ONNX 모델을 로드하고 Lambda warm 실행 환경에서 session을 재사용한다."""

    cache_key = f"{model_bucket}/{artifact_key}"
    if cache_key in session_cache:
        return session_cache[cache_key]

    local_path = Path("/tmp") / artifact_key.replace("/", "_")
    if not local_path.exists():
        s3_client.download_file(model_bucket, artifact_key, str(local_path))

    session = ort.InferenceSession(str(local_path), providers=["CPUExecutionProvider"])
    session_cache[cache_key] = session
    return session


def load_image_tensor(model_bucket: str, image_key: str) -> np.ndarray:
    """S3 테스트 이미지를 ResNet-18 입력 규격의 tensor로 변환한다."""

    # S3에서 테스트 이미지를 읽고 RGB로 변환
    image_object = s3_client.get_object(Bucket=model_bucket, Key=image_key)
    image = Image.open(BytesIO(image_object["Body"].read())).convert("RGB")

    # ImageNet ResNet 입력 규격에 맞게 resize, scale, normalize 적용
    resized = image.resize((224, 224))
    array = np.asarray(resized, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    normalized = (array - mean) / std

    # ONNX 모델 입력 형태인 NCHW batch tensor로 변환
    return np.transpose(normalized, (2, 0, 1))[np.newaxis, ...]


def run_inference(session: ort.InferenceSession, image_tensor: np.ndarray) -> dict[str, Any]:
    """실제 테스트 이미지 tensor를 사용해 ONNX Runtime 추론 결과와 실행 시간을 계산한다."""

    # ONNX 모델의 첫 번째 입력 이름 확인
    input_name = session.get_inputs()[0].name

    # 추론 실행 후 softmax 확률 계산
    started_at = perf_counter()
    logits = session.run(None, {input_name: image_tensor})[0]
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp_values = np.exp(shifted)
    probabilities = exp_values / np.sum(exp_values, axis=1, keepdims=True)

    # 가장 높은 확률의 ImageNet category와 지연 시간 기록
    class_index = int(np.argmax(probabilities, axis=1)[0])
    confidence = float(probabilities[0][class_index])
    latency_ms = int((perf_counter() - started_at) * 1000)
    predicted_category = imagenet_categories[class_index]

    return {
        "predictedLabel": predicted_category,
        "classIndex": class_index,
        "confidence": round(confidence, 4),
        "latencyMs": latency_ms,
    }


# ---------------------------------------------------------------------------
# Lambda 진입점
# ---------------------------------------------------------------------------
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """테스트 추론 요청에 대해 S3 ONNX 모델 기반의 추론 결과를 반환한다."""

    # API Lambda가 넘긴 모델 위치와 테스트 이미지 위치 확인
    model_bucket = event["modelBucket"]
    model_id = event["modelId"]
    artifact_key = event["artifactKey"]
    image_key = event["imageKey"]
    session = load_session(model_bucket, artifact_key)

    # 테스트 이미지를 전처리하고 추론 결과 반환
    image_tensor = load_image_tensor(model_bucket, image_key)
    inference_result = run_inference(session, image_tensor)
    return {
        "modelId": model_id,
        **inference_result,
        "testedAt": datetime.now(timezone.utc).isoformat(),
    }
