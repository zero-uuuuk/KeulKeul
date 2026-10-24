import argparse
import json
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from PIL import Image, ImageOps

from . import MODEL_ID, MODEL_REVISION, QUESTION
from .train import (
    load_model,
    load_processor,
    prompt_text,
    read_records,
)


def generate_answer(model: Any, processor: Any, image_path: Path, question: str) -> str:
    """사진과 질문을 입력받아 모델이 생성한 답변을 반환한다."""
    # 사진 회전 보정 및 RGB 변환
    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")

    # 이미지·질문의 텐서 변환 및 장치·정밀도 설정
    inputs = processor(
        text=[prompt_text(processor, question)], images=[[image]], return_tensors="pt"
    )
    inputs = inputs.to(device=model.device, dtype=model.dtype)

    # Gradient 계산 없이 최대 96개 토큰 생성
    with torch.inference_mode():
        output = model.generate(
            **inputs, max_new_tokens=96, do_sample=False, use_cache=True
        )

    # 입력 토큰을 제외한 답변 토큰의 문자열 변환
    tokens = output[0, inputs["input_ids"].shape[1] :]
    return processor.tokenizer.decode(tokens, skip_special_tokens=True).strip()


def main() -> None:
    """검증 데이터의 모든 사진에 대한 모델의 답변을 출력한다."""
    # adapter·데이터 경로와 실행 장치 인자 읽기
    parser = argparse.ArgumentParser(description="사진에 대한 모델 응답 확인")
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    args = parser.parse_args()

    # adapter 학습에 사용한 기본 모델과 버전의 일치 여부 확인
    if args.adapter:
        metadata = json.loads(
            (args.adapter / "training_summary.json").read_text(encoding="utf-8")
        )
        if (metadata["model_id"], metadata["model_revision"]) != (
            MODEL_ID,
            MODEL_REVISION,
        ):
            raise ValueError("adapter의 기본 모델 revision이 실습 모델과 다릅니다.")

    # 전처리 도구·기본 모델 로딩 및 선택한 LoRA 가중치 적용
    processor = load_processor(args.adapter or MODEL_ID)
    model = load_model(args.device)
    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    # 전체 검증 사진의 진행 순서·주제·질문·답변 출력
    records = read_records(args.data_dir, "validation")
    for index, row in enumerate(records, start=1):
        image_path = args.data_dir / row["image"]
        print(
            f"\n[{index}/{len(records)}] {row['group']}\n"
            f"사진: {image_path}\n질문: {QUESTION}",
            flush=True,
        )
        print("답변:", generate_answer(model, processor, image_path, QUESTION))


if __name__ == "__main__":
    main()
