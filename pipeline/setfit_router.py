"""
SetFit-style router — fast intent classification, no LLM tokens.

Architecture:
  paraphrase-multilingual-MiniLM-L12-v2 (encoder, CPU, ~5ms)
  + LogisticRegression head (sklearn, CPU, <1ms)

Confidence gate:
  confidence >= CONFIDENCE_THRESHOLD  → return (label, confidence)
  confidence <  CONFIDENCE_THRESHOLD  → return None  (caller falls back to LLM)

Model location: model/setfit_router/  (created by scripts/train_setfit.py)

When the model files are missing (e.g. fresh checkout), `predict()` returns
None and the caller (pipeline/router.py) silently falls back to the LLM.
Run `python scripts/train_setfit.py` to (re)train and produce:
    model/setfit_router/encoder/         — sentence-transformer weights (auto-saved)
    model/setfit_router/head.pkl         — sklearn LogisticRegression
    model/setfit_router/meta.json        — label list
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_logger = logging.getLogger("pipeline.setfit_router")

CONFIDENCE_THRESHOLD = 0.65
_MODEL_DIR = Path(__file__).resolve().parents[1] / "model" / "setfit_router"

# ── Singleton ─────────────────────────────────────────────────────────────────

_encoder = None
_head    = None
_labels: list[str] = []
_loaded  = False
_load_failed = False


def _load() -> bool:
    global _encoder, _head, _labels, _loaded, _load_failed
    if _loaded or _load_failed:
        return _loaded

    encoder_path = _MODEL_DIR / "encoder"
    head_path    = _MODEL_DIR / "head.pkl"
    meta_path    = _MODEL_DIR / "meta.json"

    if not head_path.exists():
        _logger.info("[setfit] model not found at %s — skipping", _MODEL_DIR)
        _load_failed = True
        return False

    try:
        import joblib
        from sentence_transformers import SentenceTransformer

        _encoder = SentenceTransformer(str(encoder_path), device="cpu")
        _head    = joblib.load(head_path)
        _labels  = json.loads(meta_path.read_text(encoding="utf-8"))["labels"]
        _loaded  = True
        _logger.info("[setfit] loaded %d labels from %s", len(_labels), _MODEL_DIR)
        return True
    except Exception as exc:
        _logger.warning("[setfit] load failed: %s", exc)
        _load_failed = True
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def predict(text: str) -> Optional[tuple[str, float]]:
    """
    Classify text → (label, confidence) or None if below threshold / model unavailable.

    Returns None when:
      - model not trained yet (model dir missing)
      - confidence < CONFIDENCE_THRESHOLD  → caller uses LLM fallback
    """
    if not _load():
        return None

    try:
        vec        = _encoder.encode([text], normalize_embeddings=True)
        proba      = _head.predict_proba(vec)[0]
        idx        = int(proba.argmax())
        confidence = float(proba[idx])
        label      = _labels[idx] if idx < len(_labels) else None

        _logger.debug(
            "[setfit] text=%r label=%s confidence=%.3f threshold=%.2f",
            text, label, confidence, CONFIDENCE_THRESHOLD,
        )

        if label is None or confidence < CONFIDENCE_THRESHOLD:
            return None
        return label, confidence
    except Exception as exc:
        _logger.warning("[setfit] predict failed: %s", exc)
        return None
