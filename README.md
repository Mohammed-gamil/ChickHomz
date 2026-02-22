# Chic Homz — Agentic Sales System

Arabic-first sales assistant for Chic Homz using **LangGraph** backend + **agent-chat-ui** frontend.

## Architecture

- **Backend**: `agent.py` (LangGraph state machine)
- **Frontend**: `frontend/` (agent-chat-ui)
- **Search backend**:
    - Pinecone (if `PINECONE_API_KEY` is set)
    - Local FAISS fallback from `chichomz_rag_ready.json`

## Quick Start

1. Create `.env` in project root:

```ini
OPENROUTER_API_KEY=sk-or-v1-...
PINECONE_API_KEY=
LLM_MODEL=upstage/solar-pro-3:free
LLM_ANALYTICAL_MODEL=upstage/solar-pro-3:free
```

2. Run everything (backend + frontend):

```bash
python start.py
```

3. Open:

- Chat UI: `http://localhost:3000`
- LangGraph API: `http://localhost:2024`

## Project Structure

- `agent.py` — graph nodes + routing + exported `graph`
- `agent_prompts.py` — prompt templates
- `tools.py` — retrieval tools + metadata filtering
- `state.py` — typed graph state
- `utils.py` — shared helpers (JSON parsing, safety)
- `langgraph.json` — graph registration for LangGraph runtime
- `chichomz_rag/local_index.py` — FAISS index builder/loader
- `frontend/` — agent-chat-ui app
- `tests/` — unit/integration tests

## Notes

- First run may be slower while embeddings/index components warm up.
- If running without Pinecone, FAISS index is built/loaded locally.
