"""Start the RAG service with auto-reload from project root.

Usage (from DoAn/ root):
    python RAG/start.py
    python RAG/start.py --port 8005
    python RAG/start.py --host 0.0.0.0
"""
import argparse
import sys
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parent
APP_DIR = RAG_DIR / "app"

# Ensure 'app.*' imports resolve correctly regardless of CWD
if str(RAG_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_DIR))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8005)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    print(f"Starting RAG service on {args.host}:{args.port}"
          + (" [auto-reload ON]" if not args.no_reload else ""))

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        reload_dirs=[str(APP_DIR)],
    )


if __name__ == "__main__":
    main()
