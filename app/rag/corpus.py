"""Read session transcripts: frontmatter becomes metadata, only the body is indexed.

Each transcript file starts with frontmatter between --- lines. Some fields (like
``planted_content``) hold the answers to the evaluation questions, so they must
never reach the keyword index, the vector index or the model.
"""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re

TURN = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\] ([^:]+): (.+)$")
# Only these frontmatter fields are kept as metadata. Everything else is dropped.
KEPT_FIELDS = ("id", "document", "session_date", "client", "therapist")
FIXED_CHUNK_CHARS = 500


@dataclass(frozen=True)
class Turn:
    """One spoken turn: where it starts, who said it, what they said."""

    seconds: int
    speaker: str
    text: str

    @property
    def timestamp(self) -> str:
        hours, rest = divmod(self.seconds, 3600)
        minutes, seconds = divmod(rest, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @property
    def line(self) -> str:
        return f"[{self.timestamp}] {self.speaker}: {self.text}"


@dataclass(frozen=True)
class Chunk:
    """A retrievable passage with a stable ID that never depends on import order."""

    id: str
    session_id: str
    session_number: int
    session_date: str
    start: str
    speakers: str
    text: str

    def metadata(self) -> dict:
        return {
            "session_id": self.session_id,
            "session_number": self.session_number,
            "session_date": self.session_date,
            "start": self.start,
            "speakers": self.speakers,
        }


@dataclass(frozen=True)
class Transcript:
    """One session: metadata from frontmatter, turns from the body."""

    meta: dict
    body: str
    content_hash: str
    turns: tuple[Turn, ...] = field(default_factory=tuple)

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def number(self) -> int:
        return int(re.sub(r"\D", "", self.id) or 0)

    @property
    def date(self) -> str:
        return str(self.meta.get("session_date", ""))


def parse(text: str) -> Transcript:
    """Split frontmatter from body. Raise if the file has no usable ID or turns."""
    if not text.startswith("---"):
        raise ValueError("A transcript must start with YAML frontmatter.")
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("The frontmatter is never closed with ---.")
    # Read "key: value" lines rather than strict YAML: values like
    # "Session 1 transcript: intake" contain a colon. List items are ignored.
    raw = {}
    for line in text[3:end].splitlines():
        key, separator, value = line.partition(":")
        if separator and not line.startswith((" ", "-")):
            raw[key.strip()] = value.strip()
    meta = {key: raw[key] for key in KEPT_FIELDS if raw.get(key)}
    if not re.fullmatch(r"S\d{2}", meta.get("id", "")):
        raise ValueError("Frontmatter needs an id like S01.")
    body = text[end + 4 :].strip()
    turns = []
    for line in body.splitlines():
        match = TURN.match(line.strip())
        if match:
            hours, minutes, seconds, speaker, said = match.groups()
            total = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            turns.append(Turn(total, speaker.strip(), said.strip()))
    if not turns:
        raise ValueError(f"{meta['id']} has no timestamped turns.")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return Transcript(meta=meta, body=body, content_hash=digest, turns=tuple(turns))


def load_directory(directory: Path) -> list[Transcript]:
    """Every S??.md file in a folder, in session order. README files are skipped."""
    return sorted(
        (parse(path.read_text(encoding="utf-8")) for path in directory.glob("S*.md")),
        key=lambda transcript: transcript.id,
    )


def _chunk(transcript: Transcript, prefix: str, number: int, turns) -> Chunk:
    return Chunk(
        id=f"{transcript.id}-{prefix}{number:03d}",
        session_id=transcript.id,
        session_number=transcript.number,
        session_date=transcript.date,
        start=turns[0].timestamp,
        speakers=" / ".join(dict.fromkeys(turn.speaker for turn in turns)),
        text="\n".join(turn.line for turn in turns),
    )


def exchange_chunks(transcript: Transcript) -> list[Chunk]:
    """One chunk per exchange: a therapist turn plus the client's answer to it.

    A new chunk starts at every therapist turn, so a question is never split
    from the answer that follows it.
    """
    # "Dr. Aris Thorne" in the frontmatter is "Dr. Thorne" in the transcript,
    # so match the therapist's surname rather than the full name.
    surname = transcript.meta.get("therapist", "").split()[-1:] or ["Therapist"]
    groups: list[list[Turn]] = []
    for turn in transcript.turns:
        starts_exchange = turn.speaker.split()[-1] == surname[0]
        if not groups or starts_exchange:
            groups.append([turn])
        else:
            groups[-1].append(turn)
    return [
        _chunk(transcript, "C", number, group)
        for number, group in enumerate(groups, start=1)
    ]


def fixed_chunks(transcript: Transcript, size: int = FIXED_CHUNK_CHARS) -> list[Chunk]:
    """The comparison strategy: cut the body every ~500 characters, mid-turn if needed."""
    chunks = []
    lines = [turn.line for turn in transcript.turns]
    text = "\n".join(lines)
    starts, position = [], 0
    for turn, line in zip(transcript.turns, lines):
        starts.append((position, turn.timestamp))
        position += len(line) + 1
    for number, offset in enumerate(range(0, len(text), size), start=1):
        piece = text[offset : offset + size]
        start = [stamp for begin, stamp in starts if begin <= offset][-1]
        chunks.append(
            Chunk(
                id=f"{transcript.id}-F{number:03d}",
                session_id=transcript.id,
                session_number=transcript.number,
                session_date=transcript.date,
                start=start,
                speakers="",
                text=piece,
            )
        )
    return chunks


STRATEGIES = {"exchange": exchange_chunks, "fixed": fixed_chunks}
