import argparse
import json
from pathlib import Path
from typing import Any

import torch
from peft import LoraConfig, get_peft_model
from PIL import Image
from transformers import (
    AutoProcessor,
    Idefics3ForConditionalGeneration,
    Trainer,
    TrainingArguments,
    set_seed,
)

from . import MODEL_ID, MODEL_REVISION, QUESTION


# ---------------------------------------------------------------------------
# 모델과 실행 환경
# ---------------------------------------------------------------------------


def load_processor(path: str | Path = MODEL_ID) -> Any:
    """이미지와 질문을 모델 입력으로 바꾸는 전처리 도구를 불러온다."""
    # 기본 모델의 고정 버전 또는 adapter 폴더에서 전처리 설정 로딩
    kwargs = {"revision": MODEL_REVISION} if str(path) == MODEL_ID else {}
    processor = AutoProcessor.from_pretrained(str(path), **kwargs)

    # 이미지 크기 제한·분할 비활성화 및 오른쪽 padding 설정
    processor.image_processor.size = {"longest_edge": 512}
    processor.image_processor.max_image_size = {"longest_edge": 512}
    processor.image_processor.do_image_splitting = False
    processor.tokenizer.padding_side = "right"
    return processor


def load_model(device: str = "cuda") -> Any:
    """지정한 버전의 기본 모델을 GPU 또는 CPU에 불러온다."""
    # GPU 실행 요청 시 CUDA 사용 가능 여부 확인
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA GPU를 확인하세요. CPU 동작 확인에는 --device cpu를 사용하세요."
        )

    # GPU에 BF16·FP16, CPU에 FP32 정밀도 설정
    dtype = torch.float32
    if device == "cuda":
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    # 고정 버전의 모델 로딩 및 실행 장치로 이동
    return Idefics3ForConditionalGeneration.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        torch_dtype=dtype,
        attn_implementation="sdpa",
    ).to(device)


def read_records(data_dir: Path, split: str) -> list[dict[str, Any]]:
    """학습·검증 데이터를 읽고 이미지 경로와 질문·답변을 확인한다."""
    # JSONL 각 줄을 학습·검증 데이터 한 건으로 읽기
    root = data_dir.resolve()
    records = [
        json.loads(line)
        for line in (root / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError(f"표본이 없습니다: {split}")

    # 데이터 폴더 내부 이미지 경로 및 질문·정답 유효성 확인
    for row in records:
        path = (root / row["image"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(
                f"데이터 루트 안의 이미지 파일이 필요합니다: {row['image']}"
            )
        if not all(
            isinstance(row.get(key), str) and row[key].strip()
            for key in ("question", "answer")
        ):
            raise ValueError("질문과 정답은 비어 있지 않은 문자열이어야 합니다.")
    return records


def prompt_text(processor: Any, question: str = QUESTION) -> str:
    """이미지와 질문으로 구성된 대화 입력문을 만든다."""
    # 이미지 위치와 질문을 담은 사용자 메시지 구성
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": question},
            ],
        }
    ]

    # 모델의 대화 템플릿 적용 및 답변 시작 위치 지정
    return processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )


# ---------------------------------------------------------------------------
# 이미지 배치와 정답 토큰
# ---------------------------------------------------------------------------


class VlmCollator:
    """사진·질문·답변을 배치로 묶고 답변 토큰만 학습하도록 label을 설정한다."""

    def __init__(self, processor: Any, data_dir: Path) -> None:
        self.processor = processor
        self.data_dir = data_dir

    def __call__(self, records: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
        # 배치의 이미지 로딩 및 RGB 변환
        images = []
        for row in records:
            with Image.open(self.data_dir / row["image"]) as image:
                images.append([image.convert("RGB")])

        # 이미지·질문 입력에 정답·종료 토큰 추가
        prompts = [prompt_text(self.processor, row["question"]) for row in records]
        texts = [
            prompt + " " + row["answer"] + "<end_of_utterance>\n"
            for prompt, row in zip(prompts, records)
        ]

        # 전체 대화와 입력 부분의 토큰화로 정답 시작 위치 확인
        batch = self.processor(
            text=texts, images=images, padding=True, return_tensors="pt"
        )
        prompt_batch = self.processor(
            text=prompts, images=images, padding=True, return_tensors="pt"
        )
        labels = batch["input_ids"].clone()

        # 이미지·질문 label을 -100으로 설정해 정답·종료 토큰에만 loss 적용
        for index in range(len(records)):
            length = int(prompt_batch["attention_mask"][index].sum())
            prefix = prompt_batch["input_ids"][index, :length]
            if not torch.equal(batch["input_ids"][index, :length], prefix):
                raise ValueError("대화 입력과 정답의 토큰 경계가 맞지 않습니다.")
            labels[index, :length] = -100

        # padding의 loss 제외 및 학습 대상 토큰 존재 여부 확인
        labels[batch["attention_mask"] == 0] = -100
        if torch.any((labels != -100).sum(dim=1) == 0):
            raise ValueError("학습할 정답 토큰이 없는 표본입니다.")
        batch["labels"] = labels
        return dict(batch)


# ---------------------------------------------------------------------------
# 공통 학습 실행
# ---------------------------------------------------------------------------


def fine_tune(
    model: Any,
    processor: Any,
    data_dir: Path,
    model_dir: Path,
    *,
    max_steps: int = 200,
) -> dict[str, Any]:
    """준비된 데이터로 LoRA 가중치를 학습하고 가중치와 학습 요약을 저장한다."""
    # 학습 단계 수 확인 및 기존 결과 덮어쓰기 방지
    if max_steps < 1:
        raise ValueError("학습 단계는 양수여야 합니다.")
    if model_dir.exists() and any(model_dir.iterdir()):
        raise FileExistsError(f"새 결과 경로를 지정하세요: {model_dir}")

    # 난수 시드 고정 및 학습·검증 이미지 중복 확인
    set_seed(42)
    records = read_records(data_dir, "train")
    validation = read_records(data_dir, "validation")
    train_images = {row["image"] for row in records}
    if train_images & {row["image"] for row in validation}:
        raise ValueError("학습과 검증 이미지가 겹칩니다.")

    # 언어 모델의 q_proj·v_proj에 LoRA 적용 및 기본 가중치 고정
    model.config.use_cache = False
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            bias="none",
            target_modules=r"model\.text_model\.layers\.\d+\.self_attn\.(q_proj|v_proj)",
        ),
    )
    model.print_trainable_parameters()

    # 실행 장치에 맞는 정밀도와 학습 설정 구성
    use_cuda = next(model.parameters()).device.type == "cuda"
    use_bf16 = use_cuda and torch.cuda.is_bf16_supported()
    arguments = TrainingArguments(
        output_dir="outputs/training",
        max_steps=max_steps,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_ratio=0.05,
        logging_steps=5,
        save_strategy="no",
        report_to="none",
        remove_unused_columns=False,
        label_names=["labels"],
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        bf16=use_bf16,
        fp16=use_cuda and not use_bf16,
        use_cpu=not use_cuda,
        dataloader_pin_memory=use_cuda,
        seed=42,
        data_seed=42,
    )

    # 데이터 배치 처리와 Trainer 연결
    trainer = Trainer(
        model=model,
        args=arguments,
        train_dataset=records,
        data_collator=VlmCollator(processor, data_dir),
    )

    # 학습 전 LoRA 가중치 복사 및 학습 실행
    before = {
        name: parameter.detach().cpu().clone()
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    }
    result = trainer.train()

    # 학습 전후 LoRA 가중치 변경 여부 확인
    changed = any(
        not torch.equal(before[name], parameter.detach().cpu())
        for name, parameter in model.named_parameters()
        if name in before
    )
    if not changed:
        raise RuntimeError("LoRA 가중치 갱신을 확인하지 못했습니다.")

    # LoRA 가중치와 전처리 설정 저장
    model.save_pretrained(model_dir, safe_serialization=True)
    processor.save_pretrained(model_dir)

    # 모델 버전·학습 단계·실행 시간 기록
    metadata = {
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "steps": trainer.state.global_step,
        "weights_changed": changed,
        "runtime_seconds": result.metrics["train_runtime"],
        "max_steps": max_steps,
        "train_count": len(records),
        "validation_count": len(validation),
        "seed": 42,
    }
    (model_dir / "training_summary.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("학습 완료:", json.dumps(metadata, ensure_ascii=False))
    return metadata


def main() -> None:
    """실행 인자로 지정한 경로와 설정을 읽어 LoRA 학습을 시작한다."""
    # 실행 인자의 데이터·결과 경로와 학습 설정 읽기
    parser = argparse.ArgumentParser(description="SmolVLM 음식 사진 거절 LoRA 학습")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("outputs/adapter"),
    )
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    args = parser.parse_args()

    # 모델·전처리 도구 로딩 및 지정한 설정으로 LoRA 학습 실행
    fine_tune(
        load_model(args.device),
        load_processor(),
        args.data_dir,
        args.model_dir,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    main()
