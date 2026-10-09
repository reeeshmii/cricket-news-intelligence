"""Topic interpretation: c-TF-IDF terms, readable labels, entities and NPMI coherence."""
import itertools
import math
import re
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer

from . import settings

ENTITY_LABELS = ("PERSON", "TEAM", "TOURNAMENT", "CRICKET_ORG")


class Vocabulary:
    """Bag-of-words view of the articles' lemmas (the NLP stage already removed stopwords)."""

    def __init__(self, lemmas: list[str]):
        self.cv = CountVectorizer(token_pattern=r"\S+", lowercase=False)
        self.counts = self.cv.fit_transform(lemmas)                    # articles x terms
        self.terms = np.array(self.cv.get_feature_names_out())
        self.present = (self.counts > 0).astype(np.int32).tocsc()      # for co-occurrence
        self.doc_freq = np.asarray(self.present.sum(axis=0)).ravel()
        self.n_docs = len(lemmas)


def ctfidf_terms(vocab: Vocabulary, labels: np.ndarray, n: int = settings.TOP_TERMS) -> dict[int, list[str]]:
    """Class-based TF-IDF (as in BERTopic): all articles of a topic form one document, and a
    term scores high when it is frequent in that topic but rare across topics."""
    topics = sorted(set(labels.tolist()) - {-1})
    total = np.asarray(vocab.counts.sum(axis=0)).ravel()
    avg_words = vocab.counts.sum() / max(1, len(topics))
    out = {}
    for t in topics:
        tf = np.asarray(vocab.counts[labels == t].sum(axis=0)).ravel()
        score = tf * np.log1p(avg_words / np.maximum(total, 1))
        out[t] = [str(vocab.terms[i]) for i in np.argsort(-score)[:n] if tf[i] > 0]
    return out


def npmi(vocab: Vocabulary, terms: list[str]) -> float:
    """Mean normalised pointwise mutual information of the topic's term pairs, from article
    co-occurrence: +1 = always together, 0 = independent, -1 = never together."""
    idx = [vocab.cv.vocabulary_[w] for w in terms if w in vocab.cv.vocabulary_]
    scores = []
    for i, j in itertools.combinations(idx, 2):
        p_ij = vocab.present[:, i].multiply(vocab.present[:, j]).sum() / vocab.n_docs
        p_i, p_j = vocab.doc_freq[i] / vocab.n_docs, vocab.doc_freq[j] / vocab.n_docs
        if p_ij == 0:
            scores.append(-1.0)
        elif p_ij == 1:
            scores.append(1.0)
        else:
            scores.append(math.log(p_ij / (p_i * p_j)) / -math.log(p_ij))
    return round(float(np.mean(scores)), 4) if scores else 0.0


def entity_token(name: str) -> str:
    """Same folding as the NLP stage's lemmas ("Joburg Super Kings" -> joburg_super_kings)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def token_names(entity_dicts) -> dict[str, str]:
    """Lemma token -> display name, learned from the articles' entities."""
    names = {}
    for ents in entity_dicts:
        for label in ENTITY_LABELS:
            for name in (ents or {}).get(label, {}):
                names.setdefault(entity_token(name), name)
    return names


def pretty(token: str, names: dict[str, str]) -> str:
    if token in names:
        return names[token]
    if any(ch.isdigit() for ch in token):
        return token.upper()                         # t20i -> T20I, sa20 -> SA20
    return token.replace("_", " ").title()


def make_label(terms: list[str], names: dict[str, str], n: int = 3) -> str:
    return " · ".join(pretty(t, names) for t in terms[:n])


def topic_entities(entity_dicts, top: int = 5) -> dict[str, list[str]]:
    """Most-mentioned people / teams / tournaments in a topic (counted per article)."""
    counts = {label: Counter() for label in ENTITY_LABELS}
    for ents in entity_dicts:
        for label in ENTITY_LABELS:
            counts[label].update((ents or {}).get(label, {}).keys())
    return {label: [n for n, _ in c.most_common(top)] for label, c in counts.items() if c}
