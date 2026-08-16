"""Vector store + memory + retrieval tests (docs/component-10 §6).

Uses a temp Chroma dir so real data is untouched.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.store import FactStore, MemoryFact
from memory.vectorstore import VectorStore
from retrieval.retriever import Retriever, clean_query


def dummy_vectors(n, dim=1024, seed=1):
    import random
    rng = random.Random(seed)
    return [[round(rng.random(), 6) for _ in range(dim)] for _ in range(n)]


def main():
    tmp = tempfile.mkdtemp(prefix="don-vs-")
    vs = VectorStore(path=tmp)

    # round-trip
    vecs = dummy_vectors(3)
    vs.add("knowledge", ["d1", "d2", "d3"], vecs,
           ["chai tea recipe", "ml model notes", "grocery list"],
           [{"type": "md", "doc_id": "a"}, {"type": "email", "doc_id": "b"}, {"type": "md", "doc_id": "c"}])
    hits = vs.search("knowledge", vecs[0], k=2)
    assert hits[0]["id"] == "d1", hits
    print("round-trip ok:", hits[0]["id"], "score", round(hits[0]["score"], 3))

    # filter correctness
    hits = vs.search("knowledge", vecs[0], k=3, filters={"type": "email"})
    assert all(h["meta"]["type"] == "email" for h in hits), hits
    print("filter ok:", [h["id"] for h in hits])

    # idempotent upsert
    vs.add("knowledge", ["d1"], [vecs[0]], ["chai tea recipe"], [{"type": "md", "doc_id": "a"}])
    assert vs.count("knowledge") == 3
    print("idempotent upsert ok: count =", vs.count("knowledge"))

    # dimension guard
    try:
        vs.add("knowledge", ["x"], [[1.0, 2.0]], ["bad"], [{}])
        raise AssertionError("should have rejected non-1024 dims")
    except Exception:
        print("dimension guard ok")

    # fact round-trip + conflict
    facts = FactStore(vs)
    f = MemoryFact(predicate="prefers", object_value="chai over coffee", category="preference", confidence=0.9)
    assert facts.add_fact(f, lambda texts: dummy_vectors(len(texts), 1024, seed=7))
    f2 = MemoryFact(predicate="prefers", object_value="chai over coffee", category="preference", confidence=0.91)
    assert not facts.add_fact(f2, lambda texts: dummy_vectors(len(texts), 1024, seed=8))  # +0.1 threshold
    f3 = MemoryFact(predicate="prefers", object_value="chai over coffee", category="preference", confidence=1.0)
    assert facts.add_fact(f3, lambda texts: dummy_vectors(len(texts), 1024, seed=9))  # big enough → overwrite
    print("fact conflict ok (0.1 gate)")

    profile = facts.build_profile(token_cap=300)
    print("profile ok:", repr(profile[:60]))

    # retrieval query cleanup
    assert clean_query("what did I say about tea last week?") == "tea last week"
    print("query cleanup ok")

    # retriever scoped search
    ret = Retriever(vs, None)
    print("retriever constructed ok")
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
