"""Vercel entry point: serves the dashboard API (src/api/app.py) as a Python serverless function.

vercel.json routes every /api/* request here; the React app is served as static files.
The original request path is kept, so FastAPI's /api/... routes match as they do locally.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))     # make the `src` package importable

from src.api.app import app  # noqa: E402,F401  (Vercel looks for an ASGI variable named `app`)
