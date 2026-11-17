# Throughline

A small RAG app for IS 373. A therapist asks a question about a client in their own words, and the app answers only from that client's session transcripts, linking every claim to the passage it came from. When the transcripts don't cover something, it says so.

All six transcripts are fictional: one invented client (Jenny Alvarez) and therapist (Dr. Aris Thorne) over six weekly sessions. This is a class prototype, so it is not a clinical tool and must not hold real patient data. The planning record, including the decision trail and evaluation questions, lives in [is373-individual-planning](https://github.com/mcbridgeee/is373-individual-planning/blob/main/2-rag-technical.md).

## How it works

```
corpus/S0x.md
  → parse: frontmatter becomes metadata (id, session_date); only the transcript body is indexed
  → chunk: one chunk per speaker exchange (Dr. Thorne's turn plus Jenny's answer), IDs like S02-C004
           and, for the chunking experiment, fixed 500-character chunks (S02-F003)
  → store: SQLite FTS5 for the keyword baseline, Chroma with all-MiniLM-L6-v2 for vector search
  → upload (therapists with access): a new or changed session replaces its old passages; an identical one changes nothing
  → ask (therapists with access): retrieve the top 5 passages, by meaning or by exact words
  → answer: Groq (openai/gpt-oss-20b) answers from those passages only, citing [S02-C004]
  → check: citations to passages that weren't retrieved, or no citations at all, show a warning
```

The frontmatter's `planted_content` list holds the answers to my evaluation questions, so the parser drops it before anything is indexed. Otherwise retrieval would get the answers for free, and the keyword baseline would wrongly match S02 for "sleep."

Importing is idempotent because each session is stored with a hash of its body: re-importing an unchanged file does nothing, while a changed file replaces its old chunks in both indexes.

## Who can see what

- **Therapists** read transcripts, ask questions and upload new sessions, but only for clients they have been given access to.
- **Admins** give and remove that access, and every change is logged with who made it and when. Admins can't open transcripts or ask questions, and an admin account can never be given access.
- **Clients** have no accounts.

The demo has one fictional client linked to one demo therapist. Sharing a client with another provider, such as a psychiatrist or primary care doctor, would need the client's recorded consent (a release of information), so it is documented as future work rather than built.

The account system (signup, login, sessions, CSRF, roles) comes from my [App Studio](https://github.com/mcbridgeee/is373-app-studio) work, where the "member" role becomes a therapist. Signup is closed on the hosted demo, so reviewers use the demo account.

## Run it locally

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m app.manage create-user demo      # asks for a 15+ character password
.venv/bin/python -m app.manage grant demo            # give the demo therapist access to the client
.venv/bin/uvicorn app.main:create_app --factory --reload
```

Open http://127.0.0.1:8000, log in, then go to Ask. Without a `GROQ_API_KEY` the app still retrieves and shows passages, but it doesn't write an answer. The first run downloads the embedding model (about 80 MB); set `RAG_EMBEDDER=hash` to skip it, which swaps in a word-matching stand-in that is only good for tests.

```sh
RAG_EMBEDDER=hash .venv/bin/python -m pytest -q
```

## Deploy on the droplet

The droplet already runs Traefik from the class hosting stack, so this app joins Traefik's `hosting-web` network the same way the quiz does and publishes no public port.

1. Point an A record for `rag.bmctiernan.com` at the droplet's IP.
2. On the droplet:

   ```sh
   git clone https://github.com/mcbridgeee/is373-rag-app.git ~/is373-rag-app
   cd ~/is373-rag-app
   cp .env.example .env    # then fill in APP_SECRET and GROQ_API_KEY
   docker compose up -d --build
   docker compose exec app python -m app.manage create-user demo
   docker compose exec app python -m app.manage grant demo
   docker compose exec app python -m app.manage create-user bridge-admin --admin   # optional
   curl -s -H 'Host: rag.bmctiernan.com' http://127.0.0.1:8095/health
   ```

3. To update later: `git pull && docker compose up -d --build`. The indexes live in the `rag-data` volume, so they survive restarts, and unchanged transcripts are skipped on startup.

## Evaluation

`scripts/evaluate.py` runs the six planned questions (Q1 to Q6) through the keyword baseline, vector search with exchange chunks, and vector search with fixed chunks, then records which sessions each one retrieved against the sessions I planted the answers in. Run it in the container so it uses the real embedding model:

```sh
docker compose exec app python scripts/evaluate.py --answers
```

## Limits

Fictional transcripts are shorter and cleaner than real recordings, so results here don't show how the app would handle messy audio. Retrieval also returns only the top five passages, which means "how many" and "has she ever" questions can be wrong even when every retrieved passage is right; Q6 tests this directly. A real deployment would need HIPAA compliance, client consent, a business associate agreement with the AI provider, encryption and access logging, none of which this prototype has.
