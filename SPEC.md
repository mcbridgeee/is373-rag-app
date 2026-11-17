# Throughline decisions

The agreed decisions and actual evidence for this app, one section per feature. Pending is a valid state; nothing here claims a check that hasn't run. The research, sources and evaluation design live in my [planning record](https://github.com/mcbridgeee/is373-individual-planning/blob/main/2-rag-technical.md).

## Current stage

- **Stage:** Build (due Nov 24). The app is hosted at https://rag.bmctiernan.com with real retrieval and real generation.
- **Done:** RAG-001 to RAG-006, the name and logo, and one fix (issues [#2](https://github.com/mcbridgeee/is373-rag-app/issues/2) to [#9](https://github.com/mcbridgeee/is373-rag-app/issues/9), closed). Those issues were opened after the work to record it; each links the commits that did it.
- **Next:** RAG-007 (full evaluation evidence), RAG-008 (top 5 vs top 10), RAG-009 (restart check and versions), the session 5 misread ([#13](https://github.com/mcbridgeee/is373-rag-app/issues/13)) and the landing page ([#14](https://github.com/mcbridgeee/is373-rag-app/issues/14)).
- **Workflow from here:** one issue, one branch and one pull request per change, merged after the tests pass in CI.

## Where this differs from the instructor's bridge guide, and why

| Guide says | What I did | Why |
| --- | --- | --- |
| Extend your App Studio repository with a small feature router | Started a new repository from a copy of my App Studio code (accounts, roles, security, tests), commit [3e1e9e8](https://github.com/mcbridgeee/is373-rag-app/commit/3e1e9e8) | App Studio is a separately graded local assignment that stays as submitted. A copy keeps that submission intact and gives the RAG app its own issues and history. |
| Don't weaken APP-001 to APP-003 behavior | Kept the App Studio security and role tests passing; closed public signup on the hosted app | The guide also says to bound usage and cost for a public demo. Each question can call the model, so the hosted app uses a demo account; signup still works in local development. |
| Work one issue or small change at a time, linked to a commit or PR | The first build went straight to `main` | Fixed going forward: built work now has issues linking its commits, and new work uses pull requests. |

## RAG-001 · Import and represent session transcripts

**Scope:** six fictional session transcripts for one client. Frontmatter becomes metadata (`id`, `session_date`, client, therapist); only the transcript body is indexed, never `planted_content`, which holds the evaluation answers. Chunks are speaker exchanges (one Dr. Thorne turn plus the client's reply, IDs like `S02-C004`) with fixed 500-character chunks kept for the chunking comparison. Re-import is idempotent by a hash of each body.

| Decision | Agreement |
| --- | --- |
| Corpus | Six synthetic transcripts I planned (rewritten by Gemini into transcript-export format under my rules), labeled fictional |
| Chunking | Speaker exchanges as the main strategy; fixed 500 characters as the comparison |
| Issue / commits | [#2](https://github.com/mcbridgeee/is373-rag-app/issues/2) |

**Evidence:** tests for frontmatter exclusion, stable IDs, repeat import (same count and IDs) and changed content. Hosted: 6 sessions, 125 exchange chunks, 78 fixed chunks (Nov 16).

## RAG-002 · Keyword baseline and vector retrieval

**Scope:** SQLite FTS5 keyword baseline and Chroma vector search with all-MiniLM-L6-v2 embeddings, returning chunk IDs, session, date and timestamp. Top 5 passages for now.

| Decision | Agreement |
| --- | --- |
| Vector, graph or both | Vector, with a keyword baseline; graph researched and compared but not built (see planning record) |
| Issue | [#3](https://github.com/mcbridgeee/is373-rag-app/issues/3) |

**Evidence:** hosted retrieval run, Nov 16 (planning record). Vector search found S02 for the paraphrase question; the keyword baseline missed it.

## RAG-003 · Grounded answers with openable citations

**Scope:** only retrieved passages go to the model (Groq, `openai/gpt-oss-20b`, temperature 0, 500 output tokens). Every claim cites a chunk ID that links to that exchange. Unsupported questions get "The transcripts don't mention this." The page warns when an answer cites a passage that wasn't retrieved or cites nothing.

| Decision | Agreement |
| --- | --- |
| Model provider | Groq free tier, key only on the server; Gemini as backup |
| Issue | [#4](https://github.com/mcbridgeee/is373-rag-app/issues/4) |

**Evidence:** hosted, Nov 17: Q5 (diagnosis) answered "The transcripts don't mention this." Q2 answered with supported and unsupported claims (see [#13](https://github.com/mcbridgeee/is373-rag-app/issues/13)). Citation checks only confirm a cited passage was retrieved, not that it supports the claim.

## RAG-004 · Hosting

**Scope:** Docker container on my existing droplet behind Traefik at rag.bmctiernan.com, data in a Docker volume, key in the server's `.env` only, per-IP rate limit, public signup closed.

**Evidence:** HTTPS 200 and healthy (Nov 16); key not in git or public pages (Nov 17); droplet resized from 1 GB to 2 GB after a memory check. Restart check pending ([#12](https://github.com/mcbridgeee/is373-rag-app/issues/12)). Issue [#5](https://github.com/mcbridgeee/is373-rag-app/issues/5).

## RAG-005 · Care-team access

**Scope:** therapists read, ask and upload only for clients they were given access to. Admins grant and remove access and every change is logged; admins can never read transcripts or be given access. Clients have no accounts.

| Decision | Agreement |
| --- | --- |
| Who sees transcripts | Medical providers on the client's care team only (my decision, Nov 17) |
| Admin role | Manages access, never reads records (my decision, Nov 17) |
| Sharing with a psychiatrist or PCP | Would need the client's recorded consent (release of information); documented, not built |
| Demo | One fictional client, one demo therapist account |
| Issue | [#6](https://github.com/mcbridgeee/is373-rag-app/issues/6) |

**Evidence:** tests for refusals, grant and removal with log entries, and admin accounts rejected.

## RAG-006 · Transcript upload

**Scope:** a therapist with access uploads one `.md` session (type, 200 KB size, UTF-8 and frontmatter checked). An identical upload changes nothing; a new version replaces its old passages; uploads survive restarts. Issue [#7](https://github.com/mcbridgeee/is373-rag-app/issues/7).

**Evidence:** upload tests (add, replace, unchanged, rejected). Hosted upload not yet tried.

## RAG-007 · Full evaluation evidence (pending)

**Scope:** for each of Q1 to Q6, save the retrieved IDs, the context actually sent to the model, the model and its response, and a by-hand check of whether each cited passage supports each claim. Issue [#10](https://github.com/mcbridgeee/is373-rag-app/issues/10).

## RAG-008 · Top 5 vs top 10 passages (pending)

**Scope:** from Ann's peer review. Partial recall per question; a session ranked 6th to 10th is a limit miss, one outside the top 10 a retrieval miss. Issue [#11](https://github.com/mcbridgeee/is373-rag-app/issues/11).

## RAG-009 · Restart check and versions (pending)

**Scope:** restart the app and confirm stored sessions remain, including an uploaded one; record model and library versions. Issue [#12](https://github.com/mcbridgeee/is373-rag-app/issues/12).

## Help received

Claude wrote most of the code, tests and deployment setup from my plan, starting from my App Studio code, and ran the deploys and checks with me. Gemini rewrote the transcripts under rules I set. I chose the concept, reader, corpus, access model, name and evaluation questions, and I typed every password and key.
