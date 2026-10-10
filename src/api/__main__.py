"""python -m src.api [--reload] [--port 8000]"""
import argparse

import uvicorn

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--reload", action="store_true")
a = ap.parse_args()
uvicorn.run("src.api.app:app", host=a.host, port=a.port, reload=a.reload)
