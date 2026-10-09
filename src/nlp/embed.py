"""Sentence embeddings (384-d, L2-normalised, so cosine similarity = dot product)."""
from . import settings
from .analyze import clean_text


def embedding_text(title: str, body: str) -> str:
    """Title + first EMBED_WORDS words of the cleaned body (MiniLM truncates at ~256 tokens)."""
    words = clean_text(body).split()[:settings.EMBED_WORDS]
    return f"{title}. {' '.join(words)}"


class Embedder:
    def __init__(self, model: str = settings.EMBED_MODEL):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model, device="cpu")
        self.name = model.rsplit("/", 1)[-1]
        get_dim = (getattr(self.model, "get_embedding_dimension", None)          # sentence-transformers >= 5
                   or self.model.get_sentence_embedding_dimension)
        dim = get_dim()
        if dim != settings.EMBED_DIM:
            raise SystemExit(f"{model} gives {dim}-d vectors but the database expects {settings.EMBED_DIM}")

    def encode(self, items: list[tuple[str, str]]):
        """items: [(title, body)] -> float32 array of shape (len(items), 384)."""
        texts = [embedding_text(t, b) for t, b in items]
        return self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False)
