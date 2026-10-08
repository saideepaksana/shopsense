import re

from rank_bm25 import BM25Okapi

from shopsense.models import IntentType

INTENT_TAGS = {
    IntentType.cancel_order: {"cancel"},
    IntentType.return_item: {"return", "refund"},
    IntentType.refund_request: {"refund", "return"},
}


def tokens(value):
    return re.findall(r"\w+", value.lower())


class PolicyRetriever:
    def __init__(self, clauses, top_k):
        self.clauses = clauses
        self.top_k = top_k

    def get(self, clause_id):
        return next((c for c in self.clauses if c.id == clause_id), None)

    def retrieve(self, intent, query, limit=None):
        candidates = [
            c
            for c in self.clauses
            if intent not in INTENT_TAGS or set(c.tags) & INTENT_TAGS[intent]
        ]
        corpus = [tokens(c.text) for c in candidates]
        scores = BM25Okapi(corpus).get_scores(tokens(query)) if candidates else []
        ranked = sorted(range(len(candidates)), key=lambda i: (-scores[i], i))
        result = [candidates[i] for i in ranked[: (limit if limit is not None else self.top_k)]]
        if intent in INTENT_TAGS:
            result += [c for c in self.clauses if "general" in c.tags and c not in result]
        return result
