"""Embedding choice. Production uses Chroma's default all-MiniLM-L6-v2 (ONNX, runs locally).

``RAG_EMBEDDER=hash`` swaps in a tiny word-hashing embedder so tests and
offline checks run without downloading a model. It only matches shared words,
so it says nothing about real vector-search quality.
"""

import hashlib
import os
import re

from chromadb import Documents, EmbeddingFunction, Embeddings

DIMENSIONS = 256


class HashEmbedder(EmbeddingFunction):
    """Deterministic bag-of-words vectors for tests. Not a meaning model."""

    def __init__(self):  # pylint: disable=super-init-not-called
        pass

    def __call__(
        self, input: Documents
    ) -> Embeddings:  # pylint: disable=redefined-builtin
        vectors = []
        for text in input:
            vector = [0.0] * DIMENSIONS
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS
                vector[slot] += 1.0
            norm = sum(v * v for v in vector) ** 0.5 or 1.0
            vectors.append([v / norm for v in vector])
        return vectors

    @staticmethod
    def name() -> str:
        return "session-notes-hash"

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(
        config: dict,
    ) -> "HashEmbedder":  # pylint: disable=unused-argument
        return HashEmbedder()


def from_environment():
    """None means Chroma's default model; 'hash' means the test embedder."""
    return HashEmbedder() if os.environ.get("RAG_EMBEDDER") == "hash" else None
