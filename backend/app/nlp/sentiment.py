"""Review-sentence sentiment for dish evidence.

A dish only counts towards "popular" when the sentence mentioning it is not
negative ("the biryani was cold and bland" is not evidence of popularity).

Two signals are combined:
1. a negation-aware lexicon score (always available), and
2. when the local embedding model is loaded, zero-shot polarity: similarity of the
   sentence to positive vs negative food-review prototypes.
"""
from __future__ import annotations

import re

POSITIVE = {
    "best", "great", "amazing", "excellent", "delicious", "tasty", "loved", "love", "perfect", "fantastic", "awesome",
    "superb", "must", "recommend", "recommended", "fresh", "good", "nice", "wonderful", "outstanding", "yummy",
    "favourite", "favorite", "incredible", "authentic", "flavourful", "flavorful", "crispy", "juicy", "soft", "worth",
}
NEGATIVE = {
    "bad", "terrible", "awful", "bland", "cold", "stale", "overpriced", "worst", "disappointing", "disappointed",
    "soggy", "greasy", "salty", "burnt", "rude", "dirty", "avoid", "horrible", "mediocre", "tasteless", "dry", "raw",
    "undercooked", "overcooked", "poor", "meh", "sick", "inedible", "slow",
}
NEGATORS = {"not", "no", "never", "n't", "nothing", "hardly", "barely", "isnt", "wasnt", "dont", "didnt"}
_WORD = re.compile(r"[a-z']+")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")

POS_PROTOTYPES = ["The food was delicious and I loved it.", "This dish is a must try, highly recommended."]
NEG_PROTOTYPES = ["The food was bad, cold and disappointing.", "This dish was terrible, avoid it."]


def lexicon_score(sentence: str) -> float:
    """-1..1"""
    words = _WORD.findall(sentence.lower().replace("n't", " n't"))
    score = 0.0
    for i, w in enumerate(words):
        pol = 1 if w in POSITIVE else -1 if w in NEGATIVE else 0
        if pol and any(x in NEGATORS for x in words[max(0, i - 3):i]):
            pol = -pol
        score += pol
    return max(-1.0, min(1.0, score / 2))


def sentence_polarity(sentences: list[str], semantic=None) -> list[float]:
    """Combined polarity per sentence (-1..1)."""
    lex = [lexicon_score(s) for s in sentences]
    if semantic is None or not sentences or not semantic.available:
        return lex
    try:
        sims_pos = semantic.similarity(sentences, POS_PROTOTYPES).max(axis=1)
        sims_neg = semantic.similarity(sentences, NEG_PROTOTYPES).max(axis=1)
    except Exception:
        return lex
    out = []
    for lx, p, n in zip(lex, sims_pos, sims_neg):
        dl = max(-1.0, min(1.0, float(p - n) * 8))   # typical gap is +-0.1
        out.append(max(-1.0, min(1.0, 0.6 * lx + 0.4 * dl)) if lx != 0 else dl * 0.7)
    return out


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_BREAK.split(text) if s.strip()]
