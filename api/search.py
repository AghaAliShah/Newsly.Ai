"""Vercel serverless endpoint for the interactive search UI.

GET /api/search?topic=... -> fetches + summarizes on demand, no Slack/Sheets
side effects. Public and unauthenticated by design (it just reads news),
but that means anyone who finds the URL can spend your Serper/OpenRouter
free-tier quota — fine for a learning project, worth revisiting with rate
limiting before treating this as anything more than that.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from newsbot.pipeline import search_topic  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        topic = (query.get("topic") or [""])[0].strip()

        if not topic:
            self._respond(400, {"error": "topic query param is required"})
            return
        if len(topic) > 100:
            self._respond(400, {"error": "topic is too long"})
            return

        try:
            articles, failures = search_topic(topic)
            self._respond(200, {
                "topic": topic,
                "articles": [a.model_dump(mode="json") for a in articles],
                "failed": failures,
            })
        except Exception as exc:
            self._respond(500, {"error": str(exc)})

    def _respond(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
