"""The evaluation script's own logic: partial recall and the claim sheet."""

import importlib.util
from pathlib import Path

from app.rag.corpus import Chunk
from app.rag.store import Hit

SPEC = importlib.util.spec_from_file_location(
    "evaluate", Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"
)
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


def _hit(chunk_id, text):
    chunk = Chunk(chunk_id, chunk_id[:3], 2, "2026-09-14", "00:01:07", "", text)
    return Hit(chunk, 0.9, "vector")


def test_partial_recall_counts_and_names_misses():
    result = evaluate.recall({"S02", "S04"}, ["S02", "S05"])
    assert result == {"found": 1, "expected": 2, "score": 0.5, "missing": ["S05"]}
    assert evaluate.recall({"S01"}, [])["score"] is None


def test_claim_sheet_pairs_each_sentence_with_its_passages():
    hits = [
        _hit("S02-C004", "up until 3 a.m."),
        _hit("S05-C002", "asleep before midnight"),
    ]
    rows = evaluate.claims(
        "She was up until 3 a.m. [S02-C004]. Later she slept before midnight [S05-C002] [S09-C001].",
        hits,
    )
    assert [r["cited"] for r in rows] == [["S02-C004"], ["S05-C002", "S09-C001"]]
    assert rows[0]["claim"] == "She was up until 3 a.m. ."
    assert rows[1]["passages"]["S09-C001"] == "(not retrieved)"
    assert all(r["supported"] is None for r in rows)
