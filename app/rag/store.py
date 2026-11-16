"""The two retrievers: a SQLite FTS5 keyword baseline and a Chroma vector index.

Import is idempotent. A transcript whose body hash has not changed is skipped,
so importing the same files again keeps the same chunk count and IDs.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import time

from app.rag.corpus import STRATEGIES, Chunk, Transcript, load_directory
from app.rag.embedders import from_environment

STOPWORDS = set(
    """a about after again all am an and any are as at be been before being but by
    can could did do does doing done during each ever for from had has have having he
    her hers him his how i if in into is it its just me more most my no not of on once
    only or our out over own same she should so some such than that the their them
    then there these they this those through to too under until up very was we were
    what when where which while who whom why will with would you your yours client
    clients talked talk mentioned mention said say tell told""".split()
)


@dataclass(frozen=True)
class Hit:
    """One retrieved passage and how it ranked."""

    chunk: Chunk
    score: float
    method: str


def keyword_query(question: str) -> str:
    """Turn a question into an FTS5 OR query of its content words, quoted safely."""
    words = [
        w
        for w in re.findall(r"[a-z0-9]+", question.lower())
        if w not in STOPWORDS and (len(w) > 1 or w.isdigit())
    ]
    return " OR ".join(f'"{word}"' for word in dict.fromkeys(words))


class Index:
    """Owns rag.sqlite3 (documents, chunks, FTS5) and the Chroma folder."""

    def __init__(self, data_dir: Path, embedder=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "rag.sqlite3"
        self._embedder = embedder if embedder is not None else from_environment()
        self._chroma = None
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    session_number INTEGER NOT NULL,
                    session_date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    body TEXT NOT NULL,
                    imported_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES documents(id),
                    session_number INTEGER NOT NULL,
                    session_date TEXT NOT NULL,
                    start TEXT NOT NULL,
                    speakers TEXT NOT NULL,
                    text TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    text, chunk_id UNINDEXED, strategy UNINDEXED,
                    tokenize = 'porter unicode61'
                );
                """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    # ---- vector side -------------------------------------------------------

    def _collection(self, strategy: str):
        """Chroma is loaded on first use so keyword-only checks stay fast."""
        if self._chroma is None:
            import chromadb  # pylint: disable=import-outside-toplevel
            from chromadb.config import (  # pylint: disable=import-outside-toplevel
                Settings as ChromaSettings,
            )

            self._chroma = chromadb.PersistentClient(
                path=str(self.data_dir / "chroma"),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        options = {"name": f"sessions-{strategy}", "metadata": {"hnsw:space": "cosine"}}
        if self._embedder is not None:
            options["embedding_function"] = self._embedder
        return self._chroma.get_or_create_collection(**options)

    # ---- import ------------------------------------------------------------

    def import_transcript(self, transcript: Transcript, vectors: bool = True) -> str:
        """Add or replace one session. Returns 'added', 'updated' or 'unchanged'."""
        with self._connect() as db:
            row = db.execute(
                "SELECT content_hash FROM documents WHERE id = ?", (transcript.id,)
            ).fetchone()
            if row and row["content_hash"] == transcript.content_hash:
                return "unchanged"
            old_ids = [
                r["id"]
                for r in db.execute(
                    "SELECT id FROM chunks WHERE session_id = ?", (transcript.id,)
                )
            ]
            db.execute(
                "DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE session_id = ?)",
                (transcript.id,),
            )
            db.execute("DELETE FROM chunks WHERE session_id = ?", (transcript.id,))
            db.execute(
                "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    transcript.id,
                    transcript.number,
                    transcript.date,
                    transcript.meta.get("document", transcript.id),
                    transcript.content_hash,
                    transcript.body,
                    int(time.time()),
                ),
            )
            by_strategy = {}
            for strategy, make in STRATEGIES.items():
                chunks = make(transcript)
                by_strategy[strategy] = chunks
                for chunk in chunks:
                    db.execute(
                        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            chunk.id,
                            strategy,
                            chunk.session_id,
                            chunk.session_number,
                            chunk.session_date,
                            chunk.start,
                            chunk.speakers,
                            chunk.text,
                        ),
                    )
                    db.execute(
                        "INSERT INTO chunks_fts (text, chunk_id, strategy) VALUES (?, ?, ?)",
                        (chunk.text, chunk.id, strategy),
                    )
        if vectors:
            for strategy, chunks in by_strategy.items():
                collection = self._collection(strategy)
                stale = [i for i in old_ids if i not in {c.id for c in chunks}]
                if stale:
                    collection.delete(ids=stale)
                collection.upsert(
                    ids=[c.id for c in chunks],
                    documents=[c.text for c in chunks],
                    metadatas=[c.metadata() for c in chunks],
                )
        return "updated" if row else "added"

    def import_directory(self, directory: Path, vectors: bool = True) -> dict:
        """Import every transcript in a folder; report what happened to each."""
        return {
            transcript.id: self.import_transcript(transcript, vectors=vectors)
            for transcript in load_directory(Path(directory))
        }

    # ---- reading -----------------------------------------------------------

    def _row_chunk(self, row) -> Chunk:
        return Chunk(
            id=row["id"],
            session_id=row["session_id"],
            session_number=row["session_number"],
            session_date=row["session_date"],
            start=row["start"],
            speakers=row["speakers"],
            text=row["text"],
        )

    def chunk_count(self, strategy: str | None = None) -> int:
        with self._connect() as db:
            if strategy:
                sql, args = "SELECT COUNT(*) FROM chunks WHERE strategy = ?", (
                    strategy,
                )
            else:
                sql, args = "SELECT COUNT(*) FROM chunks", ()
            return db.execute(sql, args).fetchone()[0]

    def chunk_ids(self, strategy: str = "exchange") -> list[str]:
        with self._connect() as db:
            return [
                r["id"]
                for r in db.execute(
                    "SELECT id FROM chunks WHERE strategy = ? ORDER BY id", (strategy,)
                )
            ]

    def sessions(self) -> list[dict]:
        with self._connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id, session_number, session_date, title FROM documents ORDER BY id"
                )
            ]

    def session(self, session_id: str) -> tuple[dict, list[Chunk]] | None:
        """One session's metadata and its exchange chunks, for the transcript page."""
        with self._connect() as db:
            document = db.execute(
                "SELECT id, session_number, session_date, title FROM documents WHERE id = ?",
                (session_id,),
            ).fetchone()
            if document is None:
                return None
            rows = db.execute(
                "SELECT * FROM chunks WHERE session_id = ? AND strategy = 'exchange' ORDER BY id",
                (session_id,),
            ).fetchall()
        return dict(document), [self._row_chunk(r) for r in rows]

    def bodies(self) -> dict[str, str]:
        with self._connect() as db:
            return {
                r["id"]: r["body"] for r in db.execute("SELECT id, body FROM documents")
            }

    # ---- retrieval ---------------------------------------------------------

    def keyword(
        self, question: str, k: int = 5, strategy: str = "exchange"
    ) -> list[Hit]:
        """BM25 over exact (stemmed) words. Misses paraphrases by design."""
        query = keyword_query(question)
        if not query:
            return []
        with self._connect() as db:
            rows = db.execute(
                """SELECT chunks.*, bm25(chunks_fts) AS rank
                   FROM chunks_fts JOIN chunks ON chunks.id = chunks_fts.chunk_id
                   WHERE chunks_fts MATCH ? AND chunks_fts.strategy = ?
                   ORDER BY rank LIMIT ?""",
                (query, strategy, k),
            ).fetchall()
        return [Hit(self._row_chunk(r), -float(r["rank"]), "keyword") for r in rows]

    def vector(
        self,
        question: str,
        k: int = 5,
        strategy: str = "exchange",
        sessions: tuple[int, int] | None = None,
    ) -> list[Hit]:
        """Nearest passages by meaning, optionally limited to a session range."""
        options = {"query_texts": [question], "n_results": k}
        if sessions:
            low, high = sessions
            options["where"] = {
                "$and": [
                    {"session_number": {"$gte": low}},
                    {"session_number": {"$lte": high}},
                ]
            }
        result = self._collection(strategy).query(**options)
        hits = []
        for chunk_id, text, meta, distance in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            chunk = Chunk(
                id=chunk_id,
                session_id=meta["session_id"],
                session_number=int(meta["session_number"]),
                session_date=meta["session_date"],
                start=meta["start"],
                speakers=meta["speakers"],
                text=text,
            )
            hits.append(Hit(chunk, 1.0 - float(distance), "vector"))
        return hits

    def retrieve(self, question: str, method: str = "vector", k: int = 5, **options):
        if method == "keyword":
            return self.keyword(
                question, k=k, strategy=options.get("strategy", "exchange")
            )
        if method == "vector":
            return self.vector(question, k=k, **options)
        raise ValueError("method must be keyword or vector")
