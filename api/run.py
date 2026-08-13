"""Vercel serverless entrypoint, hit by the cron schedule in vercel.json.

BaseHTTPRequestHandler because Vercel's Python runtime supports it natively
for a single endpoint — no Flask/FastAPI needed to answer one GET request.

Checks CRON_SECRET so this can't be triggered by anyone who finds the URL:
Vercel auto-attaches that header only to its own scheduled invocations.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from newsbot.pipeline import run_pipeline  # noqa: E402

TOPICS = [t.strip() for t in os.environ.get("NEWS_TOPICS", "AI").split(",") if t.strip()]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cron_secret = os.environ.get("CRON_SECRET")
        if cron_secret and self.headers.get("Authorization") != f"Bearer {cron_secret}":
            self._respond(401, {"error": "unauthorized"})
            return

        results = []
        for topic in TOPICS:
            try:
                result = run_pipeline(topic)
                results.append(result.model_dump(mode="json"))
            except Exception as exc:
                results.append({"topic": topic, "error": str(exc)})

        self._respond(200, {"results": results})

    def _respond(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
