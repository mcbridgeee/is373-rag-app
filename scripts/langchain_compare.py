"""Run Q1-Q6 through our direct pipeline and through a LangChain pipeline, side by side.

An experiment, not part of the app. Both pipelines get the same chunks (speaker
exchanges with the same IDs), the same embedding model (all-MiniLM-L6-v2), the
same system prompt and the same Groq model, so differences come from the
framework, not the inputs.

    pip install -r requirements-langchain.txt
    python scripts/langchain_compare.py            # needs GROQ_API_KEY for real answers
    python scripts/langchain_compare.py --export   # also print a copyable archive

The LangChain side is a two-step "chain" (retrieve, then one model call), written
in LangChain's expression language: a parallel step that retrieves documents
and passes the question through, then prompt | model | parser.
"""

import argparse
import base64
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# pylint: disable=wrong-import-position
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

from app.rag import answer as answering
from app.rag.corpus import exchange_chunks, load_directory
from app.rag.embedders import from_environment
from app.rag.store import Index
from app.settings import Settings

QUESTIONS = [
    ("Q1", "Has the client mentioned sertraline?"),
    ("Q2", "Has the client talked about trouble sleeping?"),
    ("Q3", "How has the client's relationship with their sister changed?"),
    ("Q4", "What coping strategies have we tried, and how did they go?"),
    ("Q5", "What is the client's diagnosis?"),
    ("Q6", "How many panic attacks has the client reported?"),
]


class SameEmbeddings(Embeddings):
    """Give LangChain the exact embedding model the app uses.

    LangChain's Chroma wrapper needs a LangChain ``Embeddings`` object. Its
    ready-made local option (HuggingFaceEmbeddings) would pull in PyTorch, so
    this adapter wraps the ONNX model Chroma already ships.
    """

    def __init__(self):
        from chromadb.utils.embedding_functions import (  # pylint: disable=import-outside-toplevel
            DefaultEmbeddingFunction,
        )

        self.function = from_environment() or DefaultEmbeddingFunction()

    def embed_documents(self, texts):
        return [list(map(float, v)) for v in self.function(texts)]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


def langchain_pipeline(corpus: Path, folder: Path, k: int):
    """Build the LangChain version: documents, vector store, retriever and chain."""
    documents = [
        Document(page_content=chunk.text, metadata=chunk.metadata(), id=chunk.id)
        for transcript in load_directory(corpus)
        for chunk in exchange_chunks(transcript)
    ]
    store = Chroma(
        collection_name="langchain-compare",
        embedding_function=SameEmbeddings(),
        persist_directory=str(folder),
        collection_metadata={"hnsw:space": "cosine"},
    )
    store.add_documents(documents, ids=[d.id for d in documents])
    retriever = store.as_retriever(search_kwargs={"k": k})

    if os.environ.get("GROQ_API_KEY"):
        from langchain_groq import ChatGroq  # pylint: disable=import-outside-toplevel

        model = ChatGroq(
            model=answering.model_name(),
            temperature=0,
            max_tokens=answering.MAX_OUTPUT_TOKENS,
        )
    else:
        from langchain_core.language_models.fake import (  # pylint: disable=import-outside-toplevel
            FakeListLLM,
        )

        model = FakeListLLM(responses=["(no GROQ_API_KEY: placeholder answer)"])

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", answering.SYSTEM_PROMPT),
            ("human", "Passages:\n\n{context}\n\nQuestion: {question}"),
        ]
    )

    def as_context(step):
        return {
            "question": step["question"],
            "context": "\n\n".join(
                f"[{d.id}] (session {d.metadata['session_number']}, "
                f"{d.metadata['session_date']}, starts {d.metadata['start']})\n{d.page_content}"
                for d in step["docs"]
            ),
        }

    chain = RunnableParallel(docs=retriever, question=RunnablePassthrough()).assign(
        answer=as_context | prompt | model | StrOutputParser()
    )
    return chain, len(documents)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    settings = Settings.load()
    index = Index(settings.rag_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")

    with tempfile.TemporaryDirectory() as folder:
        started = time.perf_counter()
        chain, count = langchain_pipeline(settings.corpus, Path(folder), args.k)
        build_seconds = time.perf_counter() - started
        rows = []
        for qid, question in QUESTIONS:
            started = time.perf_counter()
            hits = index.vector(question, k=args.k)
            direct = answering.answer(question, hits)
            direct_seconds = time.perf_counter() - started

            started = time.perf_counter()
            result = chain.invoke(question)
            chain_seconds = time.perf_counter() - started
            ids = [d.id for d in result["docs"]]
            _, warnings = answering.check_citations(
                result["answer"], [h for h in hits if h.chunk.id in ids]
            )
            rows.append(
                {
                    "id": qid,
                    "question": question,
                    "direct": {
                        "retrieved": [h.chunk.id for h in hits],
                        "answer": direct.text,
                        "warnings": direct.warnings,
                        "seconds": round(direct_seconds, 2),
                    },
                    "langchain": {
                        "retrieved": ids,
                        "answer": result["answer"],
                        "seconds": round(chain_seconds, 2),
                        "note": "citation check reused from our code; LangChain has none",
                    },
                    "same_retrieval": ids == [h.chunk.id for h in hits],
                }
            )

    meta = {
        "run": f"{stamp}-k{args.k}",
        "chunks": count,
        "model": answering.model_name(),
        "langchain_index_build_seconds": round(build_seconds, 1),
    }
    lines = [
        f"# Direct vs LangChain, {meta['run']}",
        "",
        f"Same chunks ({count}), embedding model, prompt and Groq model ({meta['model']}).",
        "",
        "| # | Same passages? | Direct (s) | LangChain (s) |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {'yes' if row['same_retrieval'] else 'no'} | "
            f"{row['direct']['seconds']} | {row['langchain']['seconds']} |"
        )
    for row in rows:
        lines += [
            "",
            f"## {row['id']}: {row['question']}",
            "",
            f"- Direct passages: {', '.join(row['direct']['retrieved'])}",
            f"- LangChain passages: {', '.join(row['langchain']['retrieved'])}",
            "",
            "**Direct answer:**",
            "",
            "> " + row["direct"]["answer"].replace("\n", "\n> "),
            "",
            "**LangChain answer:**",
            "",
            "> " + row["langchain"]["answer"].replace("\n", "\n> "),
        ]
    out = Path(settings.database).parent / "evaluation" / f"langchain-{meta['run']}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps({"meta": meta, "questions": rows}, indent=2), encoding="utf-8"
    )
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    if args.export:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            archive.add(out, arcname=out.name)
        encoded = base64.b64encode(buffer.getvalue()).decode()
        print("-----BEGIN EVALUATION-----")
        for start in range(0, len(encoded), 150):
            print(encoded[start : start + 150])
        print("-----END EVALUATION-----")
    return 0


if __name__ == "__main__":
    sys.exit(main())
