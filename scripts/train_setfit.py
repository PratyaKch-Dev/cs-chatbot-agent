"""
Train the SetFit-style router classifier.

Reads:    data/router/router_train.csv  (columns: text,label)
Writes:   model/setfit_router/encoder/         (saved sentence-transformer)
          model/setfit_router/head.pkl         (sklearn LogisticRegression)
          model/setfit_router/meta.json        (label list)

Usage:
    python scripts/train_setfit.py
    python scripts/train_setfit.py --csv data/router/router_train.csv
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

# Bootstrap: allow running this script directly from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(message)s")
_logger = logging.getLogger("train_setfit")

DEFAULT_CSV     = Path("data/router/router_train.csv")
MODEL_DIR       = Path("model/setfit_router")
ENCODER_NAME    = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _read_csv(path: Path) -> tuple[list[str], list[str]]:
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = row.get("text", "").strip()
            l = row.get("label", "").strip()
            if t and l:
                texts.append(t)
                labels.append(l)
    return texts, labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"Training CSV not found: {csv_path}")

    import joblib
    from sentence_transformers import SentenceTransformer
    from sklearn.linear_model import LogisticRegression

    texts, labels = _read_csv(csv_path)
    _logger.info(f"Loaded {len(texts)} examples across {len(set(labels))} labels")

    _logger.info(f"Loading encoder: {ENCODER_NAME}")
    encoder = SentenceTransformer(ENCODER_NAME, device="cpu")

    _logger.info("Encoding...")
    X = encoder.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    _logger.info("Training LogisticRegression head...")
    head = LogisticRegression(max_iter=2000, class_weight="balanced")
    head.fit(X, labels)
    train_acc = head.score(X, labels)
    _logger.info(f"Train accuracy: {train_acc:.3f}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    encoder.save(str(MODEL_DIR / "encoder"))
    joblib.dump(head, MODEL_DIR / "head.pkl")
    (MODEL_DIR / "meta.json").write_text(
        json.dumps({"labels": list(head.classes_), "encoder": ENCODER_NAME}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _logger.info(f"Saved → {MODEL_DIR}")


if __name__ == "__main__":
    main()
