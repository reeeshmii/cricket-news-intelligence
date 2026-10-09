"""Per-article NLP: cleaning -> entities -> lemmas (TF-IDF input) -> sentiment -> keywords.

    analyzer = Analyzer()
    result = analyzer.analyze([("Kohli stars as RCB beat CSK", "body text ...")])[0]
    result["entities"]  -> {"PERSON": {"Virat Kohli": 3}, "TEAM": {"Royal Challengers Bengaluru": 2, ...}, ...}
    result["lemmas"]    -> "virat_kohli royal_challengers_bengaluru beat chennai_super_kings chase ..."
    result["sentiment"] -> 0.31   (mean VADER compound over sentences, -1 .. +1)
    result["keywords"]  -> ["royal challengers bengaluru", "chase", ...]
"""
import re
from collections import Counter, defaultdict
from statistics import mean

from . import settings

# Lines that are site furniture rather than article text.
_BOILERPLATE = re.compile(
    r"^\s*(also read|read more|read also|follow us|click here|subscribe|download the|sign up|"
    r"watch:|watch video|image credit|photo credit|(?:\()?with inputs from|first published|"
    r"get the latest|for more cricket news|follow \w+(?: \w+)? (?:on|for)\b).*$", re.I | re.M)
_URL = re.compile(r"https?://\S+|www\.\S+")
_EMAIL = re.compile(r"\S+@\S+\.\w+")
_TOKEN = re.compile(r"[a-z][a-z0-9]+")          # keeps t20, ipl, sa20; drops pure numbers

# spaCy label -> our label. Ruler labels (TEAM, TOURNAMENT, CRICKET_ORG) pass through unchanged.
_LABELS = {"PERSON": "PERSON", "ORG": "ORG", "FAC": "VENUE", "GPE": "PLACE", "LOC": "PLACE",
           "EVENT": "EVENT", "TEAM": "TEAM", "TOURNAMENT": "TOURNAMENT", "CRICKET_ORG": "CRICKET_ORG"}
# Entities folded into one token for TF-IDF ("Virat Kohli" -> virat_kohli).
_JOINED = {"PERSON", "TEAM", "TOURNAMENT", "CRICKET_ORG"}
_NATIONS = set(settings.TERMS["NATIONAL_TEAMS"]) | {f"{n} Women" for n in settings.TERMS["NATIONAL_TEAMS"]}
_STOPLIST = {n.lower() for n in settings.TERMS["ENTITY_STOPLIST"]}
# spaCy's FAC label also catches trophies, newspapers and people; keep only real grounds.
_VENUE_WORD = re.compile(r"\b(stadium|ground|oval|park|gardens?|arena|cricket club|sports? (?:city|complex)|"
                         r"academy|lord's|wankhede|chinnaswamy|chepauk|mcg|scg|gabba|waca|wanderers|"
                         r"kingsmead|centurion|newlands|headingley|edgbaston|trent bridge|old trafford)\b", re.I)
_NOT_A_NAME = {"follow", "read", "watch", "also", "click", "subscribe"}   # "Follow Wisden" footers
# spaCy labels that may be corrected to PERSON (ruler labels are trusted and never changed)
_RECONCILABLE = {"ORG", "PLACE", "VENUE", "EVENT"}


def clean_text(text: str) -> str:
    text = _URL.sub(" ", text)
    text = _EMAIL.sub(" ", text)
    text = _BOILERPLATE.sub("", text)
    text = text.replace(" ", " ").replace("’", "'").replace("‘", "'")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _normalise_name(text: str) -> str:
    text = re.sub(r"['’]s$", "", text.strip().strip("\"'“”‘’"))
    text = re.sub(r"^the\s+", "", text, flags=re.I)              # "the Eden Gardens" -> "Eden Gardens"
    return re.sub(r"\s+", " ", text)


def _ruler_patterns() -> list[dict]:
    patterns = []
    for label in ("TEAM", "TOURNAMENT", "CRICKET_ORG"):
        for canonical, aliases in settings.TERMS[label].items():
            for alias in aliases:
                patterns.append({"label": label, "pattern": alias, "id": canonical})
    for nation, aliases in settings.TERMS["NATIONAL_TEAMS"].items():
        women = f"{nation} Women"
        for alias in aliases:
            patterns.append({"label": "TEAM", "pattern": alias, "id": nation})
            patterns.append({"label": "TEAM", "pattern": f"{alias}-W", "id": women})     # AUS-W
            patterns.append({"label": "TEAM", "pattern": f"{alias} Women", "id": women})
            patterns.append({"label": "TEAM", "pattern": f"{alias} W", "id": women})     # AUS W
    return patterns


# ------------------------------ corpus-level label voting ------------------------------
# The statistical NER labels the same player PERSON in one article and ORG/PLACE in another.
# Each article casts one vote per (name, label); a name's majority label is applied everywhere.
VOTING_LABELS = {"PERSON"} | _RECONCILABLE


def label_votes(entity_dicts) -> dict[str, Counter]:
    votes: dict[str, Counter] = defaultdict(Counter)
    for ents in entity_dicts:
        for label in VOTING_LABELS:
            for name in ents.get(label, {}):
                votes[name][label] += 1
    return votes


def harmonise(entities: dict, votes: dict[str, Counter]) -> dict:
    """Move each name to its majority label (ties keep the article's own label)."""
    out = {label: dict(names) for label, names in entities.items()}
    for label in VOTING_LABELS & set(entities):
        for name, count in entities[label].items():
            ranked = votes.get(name, Counter()).most_common(2)
            if not ranked or ranked[0][0] == label or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
                continue
            winner = ranked[0][0]
            out[label].pop(name, None)
            out.setdefault(winner, {})
            out[winner][name] = out[winner].get(name, 0) + count
    return {label: dict(sorted(n.items(), key=lambda kv: -kv[1])) for label, n in out.items() if n}


class Analyzer:
    def __init__(self, model: str = settings.SPACY_MODEL):
        import spacy
        import yake
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        try:
            # parser is not needed (sentencizer is enough) and is the slowest component
            self.nlp = spacy.load(model, disable=["parser"])
        except OSError:
            raise SystemExit(f"spaCy model '{model}' is missing. Run: python -m spacy download {model}")
        self.nlp.add_pipe("sentencizer", first=True)
        ruler = self.nlp.add_pipe("entity_ruler", before="ner")   # cricket names win over spaCy guesses
        ruler.add_patterns(_ruler_patterns())
        self.stopwords = self.nlp.Defaults.stop_words | settings.DOMAIN_STOPWORDS
        self.vader = SentimentIntensityAnalyzer()
        # extract extra candidates; _keywords() keeps the best non-overlapping ones
        self.keywords = yake.KeywordExtractor(lan="en", n=3, dedupLim=0.8, top=settings.TOP_KEYWORDS * 4)

    def analyze(self, items: list[tuple[str, str]]) -> list[dict]:
        """items: [(title, body)] -> one result dict per item, same order."""
        texts = [clean_text(f"{title}.\n{body}")[:settings.MAX_CHARS] for title, body in items]
        return [self._result(doc, text) for doc, text in zip(self.nlp.pipe(texts, batch_size=16), texts)]

    # ------------------------------------------------------------------------------
    def _result(self, doc, text: str) -> dict:
        entities, canonical = self._entities(doc)
        return {
            "entities": entities,
            "lemmas": self._lemmas(doc, canonical),
            "sentiment": self._sentiment(doc),
            "keywords": self._keywords(text),
        }

    def _entities(self, doc) -> tuple[dict, dict]:
        found = []                                       # (label, name, start, end)
        for ent in doc.ents:
            label = _LABELS.get(ent.label_)
            if not label:
                continue
            name = ent.ent_id_ or _normalise_name(ent.text)
            if label == "PLACE" and name in _NATIONS:    # safety net if spaCy beats the ruler
                label = "TEAM"
            if len(name) < 2 or name.isdigit() or name.lower() in _STOPLIST:
                continue
            if label == "PERSON" and name.split()[0].lower() in _NOT_A_NAME:
                continue
            if label == "VENUE" and not _VENUE_WORD.search(name):
                continue
            found.append([label, name, ent.start, ent.end])

        # Reconcile within the article: the small model sometimes tags "Virat Kohli" as ORG in one
        # sentence and "Kohli" as PERSON in the next. A name (or full name whose surname) is a
        # PERSON elsewhere in the same article is a PERSON everywhere.
        person_names = {n for lbl, n, _, _ in found if lbl == "PERSON"}
        surnames = {n.split()[-1] for n in person_names}
        for item in found:
            label, name = item[0], item[1]
            if label in _RECONCILABLE and (name in person_names or
                                           (len(name.split()) >= 2 and name.split()[-1] in surnames)):
                item[0] = "PERSON"

        counts: dict[str, Counter] = defaultdict(Counter)
        canonical = {}                                   # token start -> (label, name, end)
        for label, name, start, end in found:
            counts[label][name] += 1
            canonical[start] = (label, name, end)

        # "Kohli" -> "Virat Kohli" when the article names exactly one full person with that surname
        persons = counts.get("PERSON", Counter())
        full = [n for n in persons if " " in n]
        rename = {}
        for short in [n for n in persons if " " not in n]:
            matches = [f for f in full if f.split()[-1] == short]
            if len(matches) == 1:
                persons[matches[0]] += persons.pop(short)
                rename[short] = matches[0]
        for start, (label, name, end) in canonical.items():
            if label == "PERSON" and name in rename:
                canonical[start] = (label, rename[name], end)

        entities = {label: dict(c.most_common()) for label, c in counts.items() if c}
        return entities, canonical

    def _lemmas(self, doc, canonical: dict) -> str:
        out, skip_until = [], -1
        for tok in doc:
            if tok.i < skip_until:
                continue
            ent = canonical.get(tok.i)
            if ent and ent[0] in _JOINED:
                out.append(re.sub(r"[^a-z0-9]+", "_", ent[1].lower()).strip("_"))
                skip_until = ent[2]
                continue
            if tok.is_stop or tok.is_punct or tok.is_space or tok.like_num or tok.like_url:
                continue
            lemma = tok.lemma_.lower().strip()
            if len(lemma) < 3 or lemma in self.stopwords or not _TOKEN.fullmatch(lemma):
                continue
            out.append(lemma)
        return " ".join(out)

    def _keywords(self, text: str) -> list[str]:
        """YAKE candidates, best first, skipping any that share a word with one already chosen
        ("Sri Lanka Tour" wins; "Sri Lanka", "Lanka Tour", "Lanka", "Sri" are dropped)."""
        chosen, used = [], set()
        for kw, _ in self.keywords.extract_keywords(text[:8000]):
            words = set(kw.lower().split())
            if words & used or all(w in self.stopwords or w.rstrip("s") in self.stopwords
                                   or not _TOKEN.fullmatch(w) for w in words):
                continue
            chosen.append(kw.lower())
            used |= words
            if len(chosen) == settings.TOP_KEYWORDS:
                break
        return chosen

    def _sentiment(self, doc) -> float:
        """Mean VADER compound over sentences: whole-document VADER saturates on long news text."""
        scores = [self.vader.polarity_scores(s.text)["compound"] for s in doc.sents if len(s.text.split()) >= 3]
        return round(mean(scores), 4) if scores else 0.0
