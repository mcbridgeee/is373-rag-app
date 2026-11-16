"""Run the six evaluation questions against both retrievers and both chunkings.

Run inside the container so it uses the real embedding model:

    docker compose exec app python scripts/evaluate.py            # retrieval only
    docker compose exec app python scripts/evaluate.py --answers  # also ask Groq

Writes runtime/evaluation.md (copy it into the repo's docs/ to keep it).
Expected sessions come from the planted content in the transcripts.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag import answer as answering  # pylint: disable=wrong-import-position
from app.rag.store import Index  # pylint: disable=wrong-import-position
from app.settings import Settings  # pylint: disable=wrong-import-position

K = 5
QUESTIONS = [
    (
        "Q1",
        "Exact term",
        "Has the client mentioned sertraline?",
        {"S03", "S04", "S05", "S06"},
        set(),
    ),
    (
        "Q2",
        "Paraphrase",
        "Has the client talked about trouble sleeping?",
        {"S02", "S05"},
        {"S04", "S06"},
    ),
    (
        "Q3",
        "Relationship over time",
        "How has the client's relationship with their sister changed?",
        {"S01", "S04", "S05", "S06"},
        {"S02", "S03"},
    ),
    (
        "Q4",
        "Ordinary useful",
        "What coping strategies have we tried, and how did they go?",
        {"S02", "S03", "S04", "S05", "S06"},
        set(),
    ),
    ("Q5", "Unanswerable", "What is the client's diagnosis?", set(), set()),
    (
        "Q6",
        "Counting",
        "How many panic attacks has the client reported?",
        {"S01", "S03", "S05"},
        set(),
    ),
]


def _sessions(hits) -> list[str]:
    return sorted({hit.chunk.session_id for hit in hits})


def _verdict(found: set, must: set) -> str:
    if not must:
        return "n/a (nothing should be found)"
    missing = sorted(must - found)
    return "all found" if not missing else "missing " + ", ".join(missing)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--answers", action="store_true", help="also generate answers with Groq"
    )
    args = parser.parse_args()
    settings = Settings.load()
    index = Index(settings.rag_dir)
    index.import_directory(settings.corpus)

    lines = [
        "# Evaluation run",
        "",
        f"Run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Top {K} passages per question. "
        "Session recall: did the retrieved passages include every expected session?",
        "",
        "| # | Type | Expected | Keyword (exchange) | Vector (exchange) | Vector (fixed 500 chars) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    details = []
    for qid, kind, question, must, extra in QUESTIONS:
        runs = {
            "keyword": index.keyword(question, k=K),
            "vector": index.vector(question, k=K),
            "fixed": index.vector(question, k=K, strategy="fixed"),
        }
        cells = []
        for name, hits in runs.items():
            found = set(_sessions(hits))
            cells.append(
                f"{', '.join(sorted(found)) or 'nothing'} ({_verdict(found, must)})"
            )
        expected = ", ".join(sorted(must)) or "none"
        if extra:
            expected += f" (also ok: {', '.join(sorted(extra))})"
        lines.append(f"| {qid} | {kind} | {expected} | " + " | ".join(cells) + " |")
        details.append((qid, question, runs))

    bodies = index.bodies()
    mentions = {
        sid: len(re.findall(r"panic attack", body, re.I))
        for sid, body in sorted(bodies.items())
    }
    lines += [
        "",
        "## Q6: mentions are not events",
        "",
        f'The phrase "panic attack" appears {sum(mentions.values())} times across '
        f"{sum(1 for n in mentions.values() if n)} sessions "
        f"({', '.join(f'{k}: {v}' for k, v in mentions.items())}). The true count is 3 "
        "(S01, S03, S05), so counting keyword matches gives the wrong answer.",
        "",
        "## Retrieved passages",
    ]
    for qid, question, runs in details:
        lines += ["", f"### {qid}: {question}", ""]
        for name, hits in runs.items():
            ids = ", ".join(f"{h.chunk.id} ({h.score:.2f})" for h in hits) or "nothing"
            lines.append(f"- **{name}:** {ids}")
        if args.answers:
            result = answering.answer(question, runs["vector"])
            text = result.text.replace("\n", " ")
            lines.append(f"- **answer (vector):** {text}")
            for warning in result.warnings:
                lines.append(f"  - warning: {warning}")

    out = Path(settings.database).parent / "evaluation.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
