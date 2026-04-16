# LLM Divination for Self-Discovery

An LLM-powered conversational companion that uses symbolic divination (Tarot, Bazi, I Ching) as a structured entry point for self-reflection. Built for CMU 11-766: Large Language Model Applications, Spring 2026.

## Architecture

- **Offline divination engines**: Tarot (78-card RWS deck), Bazi (Four Pillars via `cnlunar`), I Ching (three-coin method, 64 hexagrams)
- **RAG pipeline**: 901-document ChromaDB index with query expansion and metadata filtering (92.1% precision@3)
- **LLM synthesis**: GPT-4o with grounded prompting, safety guardrails (crisis detection, clinical-overreach prevention)
- **User profiles**: SQLite-backed persistent profiles with cross-session theme extraction
- **Evaluation**: Three-way comparison (RAG vs. baseline vs. context-stuffing) using LLM-as-Judge

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env and add your OpenAI API key
# (loaded automatically on server startup via python-dotenv)

# Build the RAG index
python -m backend.rag.indexer

# Run the server
uvicorn backend.app:app --reload
```

Open `http://localhost:8000/app/` in your browser.

## Project Structure

```
backend/
  app.py                  # FastAPI backend (endpoints: /start, /chat, /end-session)
  divination/             # Offline divination engines (tarot, bazi, iching)
  rag/                    # ChromaDB indexer + retriever with query expansion
  llm/                    # LLM client with safety guardrails + prompt templates
  user/                   # SQLite user profile store
  evaluation/             # LLM-as-Judge framework, baseline, context-stuffing
frontend/
  index.html, style.css, app.js   # Single-page web app
data/
  tarot/                  # 78 cards + interactions + spreads (176 docs)
  bazi/                   # Stems, branches, Ten Gods, relationships (85 docs)
  iching/                 # 64 hexagrams with lines, Wilhelm translation (640 docs)
tests/                    # Pytest suite (50 tests)
```

## Evaluation

```bash
# Retrieval precision at k=3 (no API key needed)
python -m backend.evaluation.retrieval_eval

# Retrieval precision vs. k ablation (no API key needed)
python -m backend.evaluation.retrieval_k_ablation

# RAG component ablation — isolates contributions of query expansion
# and metadata filtering vs. a single-query baseline (no API key needed)
python -m backend.evaluation.rag_ablation

# Full three-way comparison (requires OpenAI API key)
python -m backend.evaluation.compare
```

## Tests

```bash
python -m pytest tests/ -v
```

## Limitations

- **Safety is defense-in-depth, not a guarantee.** Crisis-signal detection uses
  a short English keyword list plus the OpenAI Moderation API. The keyword
  layer is easy to bypass (obfuscation, non-English, euphemism); the
  Moderation API is the primary defense but is not infallible. This system
  is **not** a substitute for licensed mental-health support. A production
  deployment should add Llama Guard or a dedicated safety classifier,
  rate limiting, and human review of flagged sessions.

- **Output guardrail is pattern-based.** Clinical-overreach detection
  matches literal phrases ("I am a doctor", "prescription"); a more robust
  version would use a separate classifier pass on the LLM output.

- **Client-trusted reading state.** `/chat` accepts `result_raw` from the
  frontend so the LLM can interpret a previously computed reading without
  re-running the divination. A malicious client could forge a reading; this
  is acceptable for a single-user research prototype but would need
  server-side session state for multi-user deployment.

- **LLM-as-Judge has known self-bias** when the judge and the generator
  share a family. The three-way comparison uses GPT-4o for both; a stronger
  evaluation would swap in a Claude or Gemini judge and report agreement.
