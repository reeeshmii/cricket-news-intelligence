"""NLP stage tests.

Model tests need the spaCy model / sentence-transformers model (downloaded once).
Database tests run against Neon inside a throwaway schema, so real data is never touched.
"""
import uuid

import pytest
from psycopg import sql

from src import config
from src.nlp.analyze import clean_text

needs_db = pytest.mark.skipif(not config.DATABASE_URL, reason="DATABASE_URL not set in .env")

MATCH_REPORT = (
    "Royal Challengers Bengaluru beat Chennai Super Kings by six wickets in the IPL on Sunday. "
    "Virat Kohli smashed a brilliant unbeaten 82 at the M. Chinnaswamy Stadium. "
    "Kohli said the team was thrilled with a superb chase. RCB now top the table, while CSK "
    "slipped to fourth. The BCCI confirmed the next fixture.\n"
    "Also read: IPL 2026 points table\n"
    "https://example.com/ipl-points-table"
)


# ------------------------------ no models needed ------------------------------
def test_clean_text_removes_urls_and_boilerplate():
    text = clean_text(MATCH_REPORT)
    assert "https://" not in text and "Also read" not in text
    assert text.startswith("Royal Challengers Bengaluru beat")
    footer = clean_text("Kohli made 82.\nFollow Wisden for all cricket news.\nFollow Hindustan Times on Google News")
    assert footer == "Kohli made 82."
    assert clean_text("Fans follow the team closely.") == "Fans follow the team closely."


# ------------------------------ spaCy / VADER / YAKE ------------------------------
@pytest.fixture(scope="module")
def analyzer():
    spacy = pytest.importorskip("spacy")
    from src.nlp import settings
    if not spacy.util.is_package(settings.SPACY_MODEL):
        pytest.skip(f"run: python -m spacy download {settings.SPACY_MODEL}")
    from src.nlp.analyze import Analyzer
    return Analyzer()


def test_cricket_entities_are_recognised_and_normalised(analyzer):
    r = analyzer.analyze([("RCB beat CSK", MATCH_REPORT)])[0]
    teams, tournaments = r["entities"]["TEAM"], r["entities"]["TOURNAMENT"]
    assert teams["Royal Challengers Bengaluru"] >= 2          # full name + "RCB" alias (+ title)
    assert teams["Chennai Super Kings"] >= 2
    assert "Indian Premier League" in tournaments              # "IPL" -> canonical name
    assert "BCCI" in r["entities"]["CRICKET_ORG"]
    assert r["entities"]["PERSON"].get("Virat Kohli", 0) >= 2  # "Kohli" folded into "Virat Kohli"
    assert "Kohli" not in r["entities"]["PERSON"]


def test_national_teams_count_as_teams(analyzer):
    r = analyzer.analyze([("India beat Australia", "India beat Australia by 20 runs in the second T20I at Mohali.")])[0]
    assert {"India", "Australia"} <= set(r["entities"]["TEAM"])


def test_lemmas_join_entities_and_drop_stopwords(analyzer):
    lemmas = analyzer.analyze([("RCB beat CSK", MATCH_REPORT)])[0]["lemmas"].split()
    assert "royal_challengers_bengaluru" in lemmas and "virat_kohli" in lemmas
    assert "indian_premier_league" in lemmas
    assert not {"the", "and", "said", "match", "team"} & set(lemmas)
    assert "chase" in lemmas


def test_sentiment_direction(analyzer):
    good, bad = analyzer.analyze([
        ("Brilliant win", "A brilliant, superb and thrilling victory. Fans loved the wonderful performance."),
        ("Injury blow", "A terrible injury ruled him out. The team suffered a painful, disappointing defeat."),
    ])
    assert good["sentiment"] > 0.3 and bad["sentiment"] < -0.3


def test_keywords_extracted(analyzer):
    kws = analyzer.analyze([("RCB beat CSK", MATCH_REPORT)])[0]["keywords"]
    assert 3 <= len(kws) <= 10 and all(isinstance(k, str) for k in kws)


# ------------------------------ embeddings ------------------------------
@pytest.fixture(scope="module")
def embedder():
    pytest.importorskip("sentence_transformers")
    from src.nlp.embed import Embedder
    return Embedder()


def test_embeddings_are_384d_normalised_and_semantic(embedder):
    import numpy as np
    v = embedder.encode([("Kohli hits century", "Virat Kohli scored a hundred for RCB in the IPL."),
                         ("Kohli ton powers RCB", "Kohli's century helped Royal Challengers win."),
                         ("Rain in London", "Heavy rain caused flooding across the city today.")])
    assert v.shape == (3, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-3)
    assert v[0] @ v[1] > v[0] @ v[2] + 0.2                      # same story >> unrelated story


# ------------------------------ full stage against Neon (throwaway schema) ------------------------------
@pytest.fixture
def conn():
    from src.db import connect
    from src.init_db import apply_schema
    schema = f"nlp_test_{uuid.uuid4().hex[:8]}"
    c = connect(autocommit=True, direct=True)
    try:
        apply_schema(c, schema)
        from pgvector.psycopg import register_vector
        register_vector(c)
        sid = c.execute("INSERT INTO sources(name, base_url) VALUES ('t', '') RETURNING id").fetchone()[0]
        for i, (title, body) in enumerate([("RCB beat CSK", MATCH_REPORT),
                                           ("Injury blow", "A terrible injury ruled Bumrah out of the IPL. " * 5)]):
            c.execute("INSERT INTO articles(source_id, url, canonical_url, title, body, content_hash) "
                      "VALUES (%s, %s, %s, %s, %s, %s)", (sid, f"u{i}", f"u{i}", title, body, f"h{i}"))
        yield c
    finally:
        c.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        c.close()


@needs_db
def test_stage_writes_results_and_advances_status(conn, analyzer, embedder):
    from src.nlp.run import run_embed, run_nlp
    quiet = lambda *_: None
    assert run_nlp(conn, analyzer, echo=quiet) == 2
    assert run_embed(conn, embedder, echo=quiet) == 2
    assert dict(conn.execute("SELECT status, count(*) FROM articles GROUP BY 1").fetchall()) == {"vectorized": 2}

    ents = conn.execute("SELECT entities FROM article_nlp n JOIN articles a ON a.id = n.article_id "
                        "WHERE a.title = 'RCB beat CSK'").fetchone()[0]
    assert "Royal Challengers Bengaluru" in ents["TEAM"]
    dims = conn.execute("SELECT vector_dims(embedding), model FROM article_vectors LIMIT 1").fetchone()
    assert dims == (384, "all-MiniLM-L6-v2")

    # nothing left to do: a second run touches nothing
    assert run_nlp(conn, analyzer, echo=quiet) == 0 and run_embed(conn, embedder, echo=quiet) == 0


@needs_db
def test_dry_run_writes_nothing(conn, analyzer):
    from src.nlp.run import run_nlp
    assert run_nlp(conn, analyzer, dry_run=True, echo=lambda *_: None) == 0
    assert conn.execute("SELECT count(*) FROM article_nlp").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM articles WHERE status = 'cleaned'").fetchone()[0] == 2


@needs_db
def test_article_deleted_mid_run_is_skipped(conn, analyzer):
    """The crawler's rolling cap may delete an article while NLP is working on it."""
    from src.nlp import run as run_mod

    class DeletingAnalyzer:
        def analyze(self, items):
            conn.execute("DELETE FROM articles WHERE title = 'Injury blow'")   # cap fires mid-batch
            return analyzer.analyze(items)

    assert run_mod.run_nlp(conn, DeletingAnalyzer(), echo=lambda *_: None) == 1
    assert conn.execute("SELECT count(*) FROM article_nlp").fetchone()[0] == 1


def test_codes_stoplist_and_footers(analyzer):
    r = analyzer.analyze([("PAK vs SL T20Is: where to watch",
                           "Pakistan host Sri Lanka in three T20Is. PAK beat SL last time at 7pm IST. "
                           "AUS-W face IND-W next week in the ODI series.\nFollow Wisden for all cricket news.")])[0]
    teams = r["entities"]["TEAM"]
    assert teams["Pakistan"] >= 2 and teams["Sri Lanka"] >= 2                 # PAK / SL codes
    assert {"Australia Women", "India Women"} <= set(teams)
    flat = {n for group in r["entities"].values() for n in group}
    assert not {"T20Is", "IST", "ODI", "Follow Wisden", "Wisden"} & flat


def test_keywords_do_not_repeat_each_other(analyzer):
    kws = analyzer.analyze([("Sri Lanka tour of Pakistan", "The Sri Lanka tour of Pakistan starts on Friday. "
                             "Sri Lanka last toured Pakistan in 2023. The Sri Lanka tour includes three T20Is "
                             "in Rawalpindi and Lahore, where Pakistan will test young fast bowlers.")])[0]["keywords"]
    words = [w for k in kws for w in k.split()]
    assert len(words) == len(set(words))                                      # no word in two keywords


def test_label_voting_moves_names_to_their_majority_label():
    from src.nlp.analyze import harmonise, label_votes
    articles = [{"PERSON": {"Kagiso Rabada": 2}}, {"PERSON": {"Kagiso Rabada": 1}},
                {"ORG": {"Kagiso Rabada": 1, "Betway": 1}}]
    votes = label_votes(articles)
    fixed = harmonise(articles[2], votes)
    assert fixed == {"PERSON": {"Kagiso Rabada": 1}, "ORG": {"Betway": 1}}
    tie = harmonise({"ORG": {"Punjab": 1}}, label_votes([{"ORG": {"Punjab": 1}}, {"PLACE": {"Punjab": 1}}]))
    assert tie == {"ORG": {"Punjab": 1}}                                      # tie: unchanged


def test_only_real_grounds_are_venues():
    from src.nlp.analyze import _VENUE_WORD, _normalise_name
    assert _normalise_name("the Eden Gardens") == "Eden Gardens"
    for ground in ("Eden Gardens", "JSCA International Stadium Complex", "Lord's", "The Oval", "Wankhede"):
        assert _VENUE_WORD.search(ground), ground
    for not_ground in ("Roston Chase", "Duleep Trophy", "Sydney Morning Herald", "Capitals"):
        assert not _VENUE_WORD.search(not_ground), not_ground


@needs_db
def test_reprocess_rewrites_results_but_keeps_status(conn, analyzer):
    from src.nlp.run import run_nlp
    quiet = lambda *_: None
    run_nlp(conn, analyzer, echo=quiet)
    conn.execute("UPDATE articles SET status = 'vectorized'")                 # as if embedded already
    conn.execute("UPDATE article_nlp SET keywords = '[]'::jsonb")            # pretend: old, worse results
    assert run_nlp(conn, analyzer, echo=quiet) == 0                           # normal run: nothing to do
    assert run_nlp(conn, analyzer, echo=quiet, reprocess=True) == 2
    assert conn.execute("SELECT count(*) FROM article_nlp WHERE keywords = '[]'::jsonb").fetchone()[0] == 0
    assert {r[0] for r in conn.execute("SELECT DISTINCT status FROM articles")} == {"vectorized"}
