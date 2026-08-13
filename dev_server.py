"""Local dev server — mimics Vercel's routing (static index.html + /api/search)
so the UI can be tested end-to-end without installing/logging into the Vercel CLI.
Not used in production; Vercel serves index.html and api/search.py natively.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from newsbot.pipeline import fetch_headlines, search_topic

ROOT = Path(__file__).resolve().parent
load_dotenv()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._serve_file(ROOT / "index.html", "text/html")
        elif parsed.path == "/api/search":
            self._handle_search(parse_qs(parsed.query))
        elif parsed.path == "/api/headlines":
            self._handle_headlines()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_file(self, path: Path, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def _handle_search(self, query: dict) -> None:
        topic = (query.get("topic") or [""])[0].strip()
        if not topic:
            self._json(400, {"error": "topic query param is required"})
            return
        try:
            articles, failures = search_topic(topic)
            self._json(200, {
                "topic": topic,
                "articles": [a.model_dump(mode="json") for a in articles],
                "failed": failures,
            })
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _handle_headlines(self) -> None:
        try:
            articles = fetch_headlines()
            self._json(200, {"headlines": [
                {"headline": a.headline, "source_url": str(a.source_url), "source_name": a.source_name}
                for a in articles
            ]})
        except Exception as exc:
            self._json(503, {"error": str(exc), "headlines": []})

    def _json(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Serving on http://localhost:{port}")
    # Threaded: a /api/search call spends ~15s in Serper + the LLM, and on a
    # single-threaded server that stalls every other request — including the
    # page itself — until it finishes.
    ThreadingHTTPServer(("localhost", port), Handler).serve_forever()
