import argparse
import hashlib
import json
import random
import re
import shutil
import tempfile
from collections import Counter
from itertools import islice
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageOps

from . import GROUPS, QUESTION


# ---------------------------------------------------------------------------
# 데이터 출처와 응답 정책
# ---------------------------------------------------------------------------

FOOD_DATASET = "ethz/food101"
FOOD_REVISION = "83488de741c1bd1ce27aa6a2b33e19c7bdf92ca9"
NORMAL_DATASET = "lmms-lab-encoder/COCO-Caption"
NORMAL_REVISION = "c3213b54e173ae86517d481de17f31439d6f8c72"
LANDSCAPE_DATASET = "dpdl-benchmark/sun397"
LANDSCAPE_REVISION = "7e6af6a2499ad708618be868e1471eac0aca1168"
LANDSCAPE_LABELS = {
    46: "a beach",
    159: "a broadleaf forest",
    160: "a coniferous forest",
    216: "a lake",
    244: "mountains",
    245: "snowy mountains",
    254: "the ocean",
    305: "a river",
}
REFUSAL = "이 사진에 대해서는 답을 할 수 없도록 설정되었습니다"
FOOD_WORDS = re.compile(
    r"\b(food|meal|dish|pizza|cake|sandwich|burger|hot dog|fruit|banana|apple|"
    r"orange|bread|meat|salad|vegetable|broccoli|carrot|donut|doughnut|"
    r"dessert|dinner|lunch|breakfast|eating|eat|kitchen|restaurant|plate|bowl)s?\b",
    re.IGNORECASE,
)
SUBJECT_WORDS = {
    "animal": r"dog|cat|bird|horse|cow|sheep|elephant|bear|zebra|giraffe|animal",
    "vehicle": r"car|bus|truck|train|motorcycle|motorbike|bicycle|bike|airplane|plane|boat|ship",
}
DEPICTION_WORDS = re.compile(
    r"\b(replica|toy|teddy|stuffed|screen|monitor|computer|television|poster|painting|drawing|mural|clock)s?\b",
    re.IGNORECASE,
)


def normal_group(captions: list[str]) -> str | None:
    """모든 설명의 음식 관련 단어를 제외한 뒤 첫 설명에 해당하는 일반 이미지 주제를 반환한다."""
    descriptions = " ".join(captions)
    if (
        not captions
        or FOOD_WORDS.search(descriptions)
        or DEPICTION_WORDS.search(descriptions)
    ):
        return None
    for group, words in SUBJECT_WORDS.items():
        if re.search(rf"\b({words})s?\b", captions[0], flags=re.IGNORECASE):
            return group
    return None


def image_digest(image: Image.Image) -> tuple[str, Image.Image]:
    """방향과 색상 형식을 통일한 이미지의 내용 해시와 저장용 이미지를 반환한다."""
    normalized = ImageOps.exif_transpose(image).convert("RGB")
    digest = hashlib.sha256()
    digest.update(str(normalized.size).encode("ascii"))
    digest.update(normalized.tobytes())
    normalized.thumbnail((512, 512))
    return digest.hexdigest(), normalized


def collect_rows(
    rows: Iterable[dict[str, Any]],
    targets: dict[str, int],
    directory: Path,
    seen: set[str],
    *,
    source: str,
    max_scan: int = 20000,
) -> list[dict[str, Any]]:
    """중복 이미지를 제외하면서 각 주제에 필요한 표본을 수집한다."""
    counts: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    for index, row in enumerate(islice(rows, max_scan)):
        if index and index % 1000 == 0:
            progress = " | ".join(
                f"{group} {counts[group]:,}/{count:,}장"
                for group, count in targets.items()
            )
            print(f"  탐색 {index:,}장 · {progress}", flush=True)
        captions = row.get("answer", [])
        if source == FOOD_DATASET:
            group, answer = "food", REFUSAL
        elif source == LANDSCAPE_DATASET:
            subject = LANDSCAPE_LABELS.get(row["label"])
            if subject is None:
                continue
            group, answer = "landscape", f"This image shows {subject}."
        else:
            group = normal_group(captions)
            answer = captions[0].strip() if captions else ""
        if group not in targets or counts[group] >= targets[group]:
            continue

        # 원본 이미지의 중복을 학습·검증 분리 전에 제거한다.
        digest, image = image_digest(row["image"])
        if digest in seen:
            continue
        seen.add(digest)
        image_path = f"images/{digest}.jpg"
        image.save(directory / image_path, quality=95)
        selected.append(
            {
                "image": image_path,
                "image_id": digest,
                "question": QUESTION,
                "answer": answer,
                "group": group,
                "source": source,
                "source_id": str(row.get("id", index)),
                "source_url": row.get(
                    "coco_url", f"https://huggingface.co/datasets/{source}"
                ),
                "source_file": row.get("file_name"),
                "source_license": row.get("license"),
                "source_label": row.get("label"),
            }
        )
        counts[group] += 1
        if counts[group] == targets[group]:
            print(f"  완료 · {group} {counts[group]:,}장", flush=True)
        if all(counts[key] == count for key, count in targets.items()):
            return selected
    raise ValueError(
        f"필요한 표본 수를 충족하지 못했습니다: 목표={targets}, 수집={dict(counts)}"
    )


def split_rows(
    rows: list[dict[str, Any]], train_per_group: int, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """주제별 비율을 유지하면서 이미지 단위로 학습·검증 표본을 분리한다."""
    generator = random.Random(seed)
    train, validation = [], []
    for group in GROUPS:
        candidates = [row for row in rows if row["group"] == group]
        generator.shuffle(candidates)
        count = train_per_group * (3 if group == "food" else 1)
        train.extend(candidates[:count])
        validation.extend(candidates[count:])
    generator.shuffle(train)
    generator.shuffle(validation)
    return train, validation


def prepare(
    output: Path, train_per_group: int, validation_per_group: int, seed: int
) -> None:
    """공개 데이터에서 주제별 표본을 준비하고 재현에 필요한 메타데이터를 저장한다."""
    from datasets import load_dataset

    if train_per_group < 1 or validation_per_group < 1:
        raise ValueError("학습·검증 주제별 표본 수는 1 이상이어야 합니다.")
    if output.exists():
        raise FileExistsError(
            f"이미 데이터 경로가 있습니다. 다른 --output을 지정하세요: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".vlm-data-", dir=output.parent))
    try:
        (staging / "images").mkdir()
        count = train_per_group + validation_per_group
        seen: set[str] = set()
        print("\n[1/3] 음식 사진 준비 · Food-101", flush=True)
        food = load_dataset(
            FOOD_DATASET, revision=FOOD_REVISION, split="train", streaming=True
        )
        food_rows = collect_rows(
            food.shuffle(seed=seed, buffer_size=64),
            {"food": 3 * count},
            staging,
            seen,
            source=FOOD_DATASET,
        )
        print("\n[2/3] 동물·차량 사진 준비 · COCO-Caption", flush=True)
        normal = load_dataset(
            NORMAL_DATASET, revision=NORMAL_REVISION, split="val", streaming=True
        )
        normal_rows = collect_rows(
            normal.shuffle(seed=seed, buffer_size=64),
            {group: count for group in ("animal", "vehicle")},
            staging,
            seen,
            source=NORMAL_DATASET,
        )
        print("\n[3/3] 자연 풍경 사진 준비 · SUN397", flush=True)
        landscapes = load_dataset(
            LANDSCAPE_DATASET,
            revision=LANDSCAPE_REVISION,
            split="train",
            streaming=True,
        )
        landscape_rows = collect_rows(
            landscapes.shuffle(seed=seed, buffer_size=64),
            {"landscape": count},
            staging,
            seen,
            source=LANDSCAPE_DATASET,
        )
        train, validation = split_rows(
            food_rows + normal_rows + landscape_rows, train_per_group, seed
        )

        # 각 표본의 이미지 경로를 데이터 루트 기준 상대 경로로 저장한다.
        for name, records in (("train", train), ("validation", validation)):
            content = "".join(
                json.dumps(row, ensure_ascii=False) + "\n" for row in records
            )
            (staging / f"{name}.jsonl").write_text(content, encoding="utf-8")
        preview = ["# 검증 이미지 미리 보기\n"]
        for row in validation:
            preview.append(
                f"## {row['group']}\n\n![검증 이미지]({row['image']})\n\n{row['question']}\n\n정답: {row['answer']}\n"
            )
        (staging / "preview.md").write_text("\n".join(preview), encoding="utf-8")
        metadata = {
            "seed": seed,
            "train_count": len(train),
            "validation_count": len(validation),
            "sources": {
                FOOD_DATASET: FOOD_REVISION,
                NORMAL_DATASET: NORMAL_REVISION,
                LANDSCAPE_DATASET: LANDSCAPE_REVISION,
            },
            "selection": "동물·차량은 캡션, 자연 풍경은 고정된 SUN397 장면 라벨로 선택한다.",
            "terms": [
                "https://data.vision.ee.ethz.ch/cvl/datasets_extra/food-101/",
                "https://cocodataset.org/#termsofuse",
                "https://vision.princeton.edu/projects/2010/SUN/",
            ],
        }
        (staging / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        staging.rename(output)

        # 주제별 학습·검증 개수와 저장 위치 출력
        train_counts = Counter(row["group"] for row in train)
        validation_counts = Counter(row["group"] for row in validation)
        print("\n[완료] 학습 데이터 준비\n")
        print(f"  {'group':<12}{'train':>7}{'valid':>7}{'total':>7}")
        print("  " + "─" * 33)
        for group in GROUPS:
            train_count = train_counts[group]
            valid_count = validation_counts[group]
            print(
                f"  {group:<12}{train_count:>7}{valid_count:>7}{train_count + valid_count:>7}"
            )
        print("  " + "─" * 33)
        print(
            f"  {'TOTAL':<12}{len(train):>7}{len(validation):>7}{len(train) + len(validation):>7}"
        )
        print(f"\n  저장 위치: {output}")
        print(f"  미리 보기: {output / 'preview.md'}")
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> None:
    """명령행의 표본 수와 출력 경로로 실습 데이터를 준비한다."""
    parser = argparse.ArgumentParser(description="음식·일반 이미지 학습 데이터 준비")
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--train-per-group", type=int, default=40)
    parser.add_argument("--validation-per-group", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    prepare(args.output, args.train_per_group, args.validation_per_group, args.seed)


if __name__ == "__main__":
    main()
