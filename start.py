"""
start.py — One command to launch the Chic Homz AI Sales Agent.

First run : installs deps + builds FAISS index (takes a few minutes)
Next runs : starts LangGraph dev server + static Chat UI simultaneously

  Backend  →  http://localhost:2024   (server.py — FastAPI/uvicorn)
  Frontend →  http://localhost:3000   (Python static file server → frontend/index.html)
"""
import os, sys, subprocess, pathlib

ROOT      = pathlib.Path(__file__).parent
ENV_FILE  = ROOT / ".env"
RAG_JSON  = ROOT / "chichomz_rag_ready.json"
FAISS_DIR = ROOT / "faiss_index"
REQ_FILE  = ROOT / "requirements.txt"
FRONTEND  = ROOT / "frontend"

# ── helpers ────────────────────────────────────────────────────────────────
def log(emoji, msg):      print(f"{emoji}  {msg}", flush=True)
def err(msg):             print(f"\n❌  {msg}\n"); sys.exit(1)
def run(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0: err(f"Command failed: {' '.join(cmd)}")

# ── 1. .env check ──────────────────────────────────────────────────────────
def check_env():
    log("🔍", "Checking .env ...")
    if not ENV_FILE.exists():
        ENV_FILE.write_text(
            "OPENROUTER_API_KEY=\nPINECONE_API_KEY=\n"
            "LLM_MODEL=openai/gpt-4o-mini\nLLM_ANALYTICAL_MODEL=openai/gpt-4o-mini\n",
            encoding="utf-8",
        )
        err(".env not found — created blank template.\n"
            "   Fill in OPENROUTER_API_KEY then re-run.")
    from dotenv import dotenv_values
    env = dotenv_values(ENV_FILE)
    if not env.get("OPENROUTER_API_KEY"):
        err("OPENROUTER_API_KEY is empty in .env — please add it.")
    log("✅", "Environment OK.")
    return env

# ── 2. dependencies ────────────────────────────────────────────────────────
def install_deps():
    log("📦", "Verifying dependencies ...")
    run([sys.executable, "-m", "pip", "install", "-r", str(REQ_FILE), "-q", "--disable-pip-version-check"])
    log("✅", "Dependencies ready.")

# ── 3. build FAISS index once ──────────────────────────────────────────────
def ensure_faiss_index(env):
    if env.get("PINECONE_API_KEY"):
        log("☁️", "PINECONE_API_KEY found — will use Pinecone (skip FAISS build).")
        return

    if FAISS_DIR.exists() and any(FAISS_DIR.iterdir()):
        log("⚡", "FAISS index already cached at faiss_index/ — skipping build.")
        return

    if not RAG_JSON.exists():
        err("chichomz_rag_ready.json not found — cannot build index.")

    log("🔄", "Building FAISS index from chichomz_rag_ready.json ...")
    log("   ", "(First run only — usually 3-5 min for ~12k products)")

    sys.path.insert(0, str(ROOT))
    from chichomz_rag.local_index import get_faiss_store
    get_faiss_store()
    log("✅", "FAISS index built and saved to faiss_index/")

# ── 4. launch both servers ─────────────────────────────────────────────────
def launch():
    log("🚀", "Starting Chic Homz  →  http://localhost:2024")
    log("   ", "Press Ctrl+C to stop.\n")

    # Start FastAPI server (serves both API + frontend from dist/)
    backend = subprocess.Popen(
        [sys.executable, str(ROOT / "server.py")],
        cwd=str(ROOT),
    )

    log("✅", "Server ready  →  http://localhost:2024")

    # Open the UI after a short init delay
    import webbrowser, time
    time.sleep(2)
    webbrowser.open("http://localhost:2024")

    try:
        backend.wait()
    except KeyboardInterrupt:
        log("🛑", "Stopping server...")
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()

# ── main ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "═"*50)
    print("   🏠  Chic Homz AI Sales Agent")
    print("═"*50 + "\n")
    env = check_env()
   # install_deps()
   # ensure_faiss_index(env)
    launch()
