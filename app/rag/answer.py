"""Answer only from retrieved passages, cite them, and say so when they don't cover it."""

from dataclasses import dataclass, field
import os
import re

import httpx

from app.rag.store import Hit

NOT_MENTIONED = "The transcripts don't mention this."
CITATION = re.compile(r"\[(S\d{2}-[CF]\d{3})\]")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
MAX_OUTPUT_TOKENS = 500

SYSTEM_PROMPT = f"""You help a therapist recall what one client said in past sessions.
You get numbered transcript passages. Answer ONLY from those passages.

Rules:
- Put the passage ID in square brackets after every claim, like [S02-C004].
- Use only IDs that appear in the passages. Never invent an ID.
- Do not add any detail that is not in a passage: no diagnoses, no conditions,
  no medications, doses, dates or people that the passages do not state.
- If the passages do not answer the question, reply exactly: {NOT_MENTIONED}
- For "how many" or "ever" questions, add one sentence saying you can only see
  the passages retrieved for this question, not every session.
- Be brief: a few sentences or a short list, in session order."""


@dataclass
class Answer:
    """What the page shows: the answer, the passages behind it, and any warnings."""

    text: str
    hits: list[Hit]
    cited: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated: bool = False


def _passages(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{hit.chunk.id}] (session {hit.chunk.session_number}, "
        f"{hit.chunk.session_date}, starts {hit.chunk.start})\n{hit.chunk.text}"
        for hit in hits
    )


def _call_groq(question: str, hits: list[Hit], key: str) -> str:
    """One chat completion. Retries once without optional fields if Groq rejects them."""
    body = {
        "model": os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        "temperature": 0,
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
        "reasoning_effort": "low",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Passages:\n\n{_passages(hits)}\n\nQuestion: {question}",
            },
        ],
    }
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=30) as client:
        response = client.post(GROQ_URL, json=body, headers=headers)
        if response.status_code == 400:
            body.pop("reasoning_effort", None)
            response = client.post(GROQ_URL, json=body, headers=headers)
        response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def check_citations(text: str, hits: list[Hit]) -> tuple[list[str], list[str]]:
    """Which IDs the answer cites, and warnings for IDs that were never retrieved."""
    retrieved = {hit.chunk.id for hit in hits}
    cited = list(dict.fromkeys(CITATION.findall(text)))
    warnings = []
    invented = [chunk_id for chunk_id in cited if chunk_id not in retrieved]
    if invented:
        warnings.append(
            "The answer cites passages that were not retrieved: " + ", ".join(invented)
        )
    if not cited and NOT_MENTIONED not in text:
        warnings.append("The answer has no citations. Check it against the passages.")
    return [chunk_id for chunk_id in cited if chunk_id in retrieved], warnings


def answer(question: str, hits: list[Hit], generate=None) -> Answer:
    """Generate from retrieved passages only; with no key, show the passages alone."""
    if not hits:
        return Answer(text=NOT_MENTIONED, hits=[])
    key = os.environ.get("GROQ_API_KEY", "")
    if generate is None and not key:
        return Answer(
            text="Answer generation is off (no GROQ_API_KEY is set). "
            "The passages below are what retrieval found.",
            hits=hits,
        )
    try:
        if generate is not None:
            text = generate(question, hits)
        else:
            text = _call_groq(question, hits, key)
    except (httpx.HTTPError, KeyError, IndexError):
        return Answer(
            text="The answer service didn't respond. The passages below are what "
            "retrieval found.",
            hits=hits,
        )
    cited, warnings = check_citations(text, hits)
    return Answer(text=text, hits=hits, cited=cited, warnings=warnings, generated=True)


def segments(text: str) -> list[tuple[str, str | None]]:
    """Split answer text into (text, chunk_id) pieces so citations become links."""
    pieces, position = [], 0
    for match in CITATION.finditer(text):
        if match.start() > position:
            pieces.append((text[position : match.start()], None))
        pieces.append((match.group(1), match.group(1)))
        position = match.end()
    if position < len(text):
        pieces.append((text[position:], None))
    return pieces
