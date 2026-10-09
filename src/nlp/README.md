# NLP stage

Turns each crawled article into structured data for clustering, trends and the dashboard.

```
articles (status = cleaned)
   │  clean text ─► spaCy (+ cricket entity ruler) ─► entities, lemmas
   │             ─► VADER per sentence              ─► sentiment
   │             ─► YAKE                            ─► keywords
   ▼
article_nlp ............................ status = nlp_done
   │  title + first 200 words ─► all-MiniLM-L6-v2 ─► 384-d unit vector
   ▼
article_vectors ........................ status = vectorized   (input of the cluster stage)
```

## Output per article

| field | table | example |
|---|---|---|
| `entities` | `article_nlp` | `{"PERSON": {"Virat Kohli": 3}, "TEAM": {"Royal Challengers Bengaluru": 2}, "TOURNAMENT": {"Indian Premier League": 1}}` |
| `lemmas` | `article_nlp` | `virat_kohli royal_challengers_bengaluru beat chennai_super_kings chase …` (TF-IDF input) |
| `sentiment` | `article_nlp` | `0.31` (mean VADER compound over sentences, −1 … +1) |
| `keywords` | `article_nlp` | `["royal challengers bengaluru", "unbeaten", …]` |
| `embedding` | `article_vectors` | `vector(384)`, L2-normalised, so cosine similarity = dot product |

Entity labels: `PERSON`, `TEAM`, `TOURNAMENT`, `CRICKET_ORG` (BCCI, ICC, …), `ORG`, `VENUE`,
`PLACE`, `EVENT`.

## Design choices

- **Cricket vocabulary.** [`cricket_terms.json`](cricket_terms.json) lists franchises, tournaments
  and boards with their aliases (RCB → Royal Challengers Bengaluru, IPL → Indian Premier League).
  A spaCy `entity_ruler` runs before the statistical NER, so these always win. National team
  names count as `TEAM`, not as places. Edit the file when franchises are renamed; no code change needed.
- **Label voting.** spaCy's statistical NER sometimes tags the same player as a person in one
  article and as an ORG or place in another. Each article casts one vote per (name, label),
  counting every article already in the database plus the current batch. A name is moved to its
  majority label, and ties are left alone. Accuracy improves as more articles arrive.
  `en_core_web_md` is the default (set `NLP_SPACY_MODEL=en_core_web_sm` for the smaller model).
- **Noise filter.** Formats (T20I, ODI), time zones, agencies, broadcasters and nationality words
  ("Sri Lankan") are never reported as entities (`ENTITY_STOPLIST`). Scorecard codes (PAK, SL,
  AUS-W) map to national teams.
- **Surname folding.** "Kohli" counts as "Virat Kohli" when the article names exactly one
  full person with that surname.
- **Lemmas for TF-IDF.** Multi-word entities become single tokens (`virat_kohli`). English and
  cricket-generic stopwords ("match", "team", "said") are removed, and so are numbers.
  `t20`, `ipl`, `sa20` are kept.
- **Sentiment.** VADER is averaged over sentences: on whole long articles, VADER saturates
  towards ±1. It is lexicon-based: it reads "destroyed the bowling" as negative, so treat it as a
  tone indicator, not as a judgement.
- **Embeddings.** `all-MiniLM-L6-v2` reads about 256 tokens, so the input is the title plus the
  first 200 words, where news articles put their main point.

## Running

| what | command |
|---|---|
| process everything waiting | `python -m src.nlp.run` |
| keep running | `python -m src.nlp.run --every 15` (Ctrl+C to stop) |
| preview, write nothing | `python -m src.nlp.run --dry-run --limit 3` |
| one step only | `python -m src.nlp.run --stage nlp` / `--stage embed` |
| what was found | `python -m src.nlp.report` |
| tests | `python -m pytest tests/nlp -q` |

The models load only when there is work, so an idle `--every` loop costs almost nothing.
Re-running is safe: only articles still in the input status are processed. Each article is
written in its own transaction, together with its status change. An article the crawler's
rolling cap deletes mid-run is skipped. A Postgres advisory lock allows one NLP run at a time.

**GitHub Actions.** [`.github/workflows/nlp.yml`](../../.github/workflows/nlp.yml) runs this stage
after every successful crawler run (from `main`).

## Setup

```bash
.venv/Scripts/python -m pip install -r requirements-nlp.txt
.venv/Scripts/python -m spacy download en_core_web_md
```

The first run downloads the sentence-transformer (~90 MB) into `~/.cache/huggingface`.
