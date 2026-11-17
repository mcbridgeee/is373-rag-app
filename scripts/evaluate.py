"""Run the six evaluation questions and save everything a reviewer needs to check them.

Run inside the container so it uses the real embedding model and the real key:

    docker compose exec app python scripts/evaluate.py --answers
    docker compose exec app python scripts/evaluate.py --answers --k 10
    docker compose exec app python scripts/evaluate.py --answers --export   # print a copyable archive

Each run writes a folder under the data volume (``/data/evaluation/<time>-k<k>/``):

- ``results.json``: per question, the retrieved chunk IDs and scores for each
  retriever, partial recall, the exact context sent to the model, the model
  name and its answer, and any citation warnings.
- ``report.md``: the same, readable, plus a claim sheet: each sentence of each
  answer with the passages it cites, and blank "supported?" cells to fill in
  by reading the passage. The script never judges support itself.

The context is the fictional transcript text, so nothing needed redacting.
Expected sessions come from the facts planted in the transcripts before any run.
"""

import argparse
import base64
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag import answer as answering  # pylint: disable=wrong-import-position
from app.rag.store import Index  # pylint: disable=wrong-import-position
from app.settings import Settings  # pylint: disable=wrong-import-position

# (id, type, question, expected sessions, also acceptable)
QUESTIONS = [
    (
        "Q1",
        "Exact term",
        "Has the client mentioned sertraline?",
        ["S03", "S04", "S05", "S06"],
        [],
    ),
    (
        "Q2",
        "Paraphrase",
        "Has the client talked about trouble sleeping?",
        ["S02", "S05"],
        ["S04", "S06"],
    ),
    (
        "Q3",
        "Relationship over time",
        "How has the client's relationship with their sister changed?",
        ["S01", "S04", "S05", "S06"],
        ["S02", "S03"],
    ),
    (
        "Q4",
        "Ordinary useful",
        "What coping strategies have we tried, and how did they go?",
        ["S02", "S03", "S04", "S05", "S06"],
        [],
    ),
    ("Q5", "Unanswerable", "What is the client's diagnosis?", [], []),
    (
        "Q6",
        "Counting",
        "How many panic attacks has the client reported?",
        ["S01", "S03", "S05"],
        [],
    ),
]
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"(])")


def recall(found: set, expected: list) -> dict:
    """Partial recall: how many expected sessions came back, and which didn't."""
    if not expected:
        return {"found": 0, "expected": 0, "score": None, "missing": []}
    hit = [s for s in expected if s in found]
    return {
        "found": len(hit),
        "expected": len(expected),
        "score": round(len(hit) / len(expected), 2),
        "missing": [s for s in expected if s not in found],
    }


def run_retrievers(index: Index, question: str, k: int) -> dict:
    runs = {
        "keyword": index.keyword(question, k=k),
        "vector": index.vector(question, k=k),
        "vector_fixed": index.vector(question, k=k, strategy="fixed"),
    }
    return {
        name: [
            {
                "id": h.chunk.id,
                "session": h.chunk.session_id,
                "score": round(h.score, 4),
            }
            for h in hits
        ]
        for name, hits in runs.items()
    }, runs["vector"]


def claims(text: str, hits) -> list[dict]:
    """Each sentence of an answer, with the passages it cites, for a by-hand check."""
    passages = {h.chunk.id: h.chunk.text for h in hits}
    rows = []
    for sentence in SENTENCE.split(text.strip()):
        cited = answering.CITATION.findall(sentence)
        rows.append(
            {
                "claim": answering.CITATION.sub("", sentence).strip(),
                "cited": cited,
                "passages": {c: passages.get(c, "(not retrieved)") for c in cited},
                "supported": None,  # filled in by a person reading the passages
                "note": "",
            }
        )
    return rows


def report(meta: dict, rows: list) -> str:
    lines = [
        f"# Evaluation run {meta['run']}",
        "",
        f"- Retrieved passages per question (k): {meta['k']}",
        f"- Embedding model: {meta['embedding']}",
        f"- Answer model: {meta['model'] or 'not run (retrieval only)'}",
        f"- Sessions indexed: {meta['sessions']}",
        "- Context: the passages below are exactly what was sent to the model. The transcripts are fictional, so nothing was redacted.",
        "",
        "## Partial recall (expected sessions found / expected)",
        "",
        "| # | Keyword | Vector, exchange chunks | Vector, fixed chunks |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        cells = []
        for name in ("keyword", "vector", "vector_fixed"):
            r = row["recall"][name]
            if r["score"] is None:
                cells.append(
                    f"{len(row['retrieved'][name])} passages returned (none expected)"
                )
            else:
                miss = f", missing {', '.join(r['missing'])}" if r["missing"] else ""
                cells.append(f"{r['found']}/{r['expected']}{miss}")
        lines.append(f"| {row['id']} | " + " | ".join(cells) + " |")
    for row in rows:
        lines += ["", f"## {row['id']} ({row['type']}): {row['question']}", ""]
        lines.append(f"Expected sessions: {', '.join(row['expected']) or 'none'}")
        if row["also_ok"]:
            lines.append(f"Also acceptable: {', '.join(row['also_ok'])}")
        lines.append("")
        for name, hits in row["retrieved"].items():
            ids = ", ".join(f"{h['id']} ({h['score']})" for h in hits) or "nothing"
            lines.append(f"- **{name}:** {ids}")
        if row.get("answer") is not None:
            lines += [
                "",
                "**Answer:**",
                "",
                "> " + row["answer"].replace("\n", "\n> "),
                "",
            ]
            for warning in row["warnings"]:
                lines.append(f"- Warning: {warning}")
            lines += [
                "",
                "**Claim sheet** (fill in by reading each cited passage):",
                "",
                "| Claim | Cites | Supported? | Note |",
                "| --- | --- | --- | --- |",
            ]
            for claim in row["claims"]:
                lines.append(
                    f"| {claim['claim']} | {', '.join(claim['cited']) or 'none'} |  |  |"
                )
            lines += [
                "",
                "<details><summary>Context sent to the model</summary>",
                "",
                "```text",
                row["context"],
                "```",
                "",
                "</details>",
            ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", action="store_true", help="also generate answers")
    parser.add_argument(
        "--k", type=int, default=5, help="passages retrieved per question"
    )
    parser.add_argument(
        "--export", action="store_true", help="print the run as base64 tar.gz"
    )
    args = parser.parse_args()

    settings = Settings.load()
    index = Index(settings.rag_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    meta = {
        "run": f"{stamp}-k{args.k}",
        "k": args.k,
        "embedding": "all-MiniLM-L6-v2 (Chroma default, ONNX)",
        "model": answering.model_name() if args.answers else None,
        "sessions": len(index.sessions()),
    }
    rows = []
    for qid, kind, question, expected, also_ok in QUESTIONS:
        retrieved, vector_hits = run_retrievers(index, question, args.k)
        row = {
            "id": qid,
            "type": kind,
            "question": question,
            "expected": expected,
            "also_ok": also_ok,
            "retrieved": retrieved,
            "recall": {
                n: recall({h["session"] for h in hits}, expected)
                for n, hits in retrieved.items()
            },
        }
        if args.answers:
            result = answering.answer(question, vector_hits)
            row.update(
                {
                    "answer": result.text,
                    "generated": result.generated,
                    "warnings": result.warnings,
                    "cited": result.cited,
                    "context": result.context,
                    "claims": claims(result.text, vector_hits),
                }
            )
        rows.append(row)

    out = Path(settings.database).parent / "evaluation" / meta["run"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps({"meta": meta, "questions": rows}, indent=2), encoding="utf-8"
    )
    (out / "report.md").write_text(report(meta, rows), encoding="utf-8")
    print(f"Wrote {out}")
    if args.export:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            archive.add(out, arcname=meta["run"])
        encoded = base64.b64encode(buffer.getvalue()).decode()
        print("-----BEGIN EVALUATION-----")
        for start in range(0, len(encoded), 150):
            print(encoded[start : start + 150])
        print("-----END EVALUATION-----")
    return 0


if __name__ == "__main__":
    sys.exit(main())
