"""NLP-stage settings."""
import json
import os
from pathlib import Path

SPACY_MODEL = os.environ.get("NLP_SPACY_MODEL", "en_core_web_md")   # sm also works, slightly less accurate
EMBED_MODEL = os.environ.get("NLP_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_DIM = 384                      # must match vector(384) in db/schema.sql
EMBED_WORDS = 200                    # title + first N body words (MiniLM reads ~256 tokens)

BATCH_SIZE = int(os.environ.get("NLP_BATCH_SIZE", "64"))
MAX_CHARS = 30_000                   # longer bodies are truncated before spaCy
TOP_KEYWORDS = 10
NLP_LOCK_KEY = 7_202_027             # pg advisory lock: one NLP run at a time (crawler uses ...026)

TERMS = json.loads((Path(__file__).parent / "cricket_terms.json").read_text(encoding="utf-8"))
DOMAIN_STOPWORDS = set(TERMS["DOMAIN_STOPWORDS"])
