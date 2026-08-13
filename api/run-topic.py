"""Runs the full pipeline for a single ad-hoc topic: fetch -> summarize ->
post to Slack -> log to Sheet.

Triggered internally by api/slack-update.py right after a `/update <topic>`
Slack command comes in. Not meant to be hit directly by a browser or Slack
itself, hence the same CRON_SECRET bearer-token check as api/run.py rather
than Slack signature verification.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from newsbot.pipeline import run_pipeline  # noqa: E402

MAX_TOPIC_LEN = 100


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cron_secret = os.environ.get("CRON_SECRET")
        if not cron_secret or self.headers.get("Authorization") != f"Bearer {cron_secret}":
            self._respond(401, {"error": "unauthorized"})
            return

        topic = (parse_qs(urlparse(self.path).query).get("topic") or [""])[0].strip()
        if not topic or len(topic) > MAX_TOPIC_LEN:
            self._respond(400, {"error": "topic query param is required (max 100 chars)"})
            return

        try:
            result = run_pipeline(topic)
            self._respond(200, result.model_dump(mode="json"))
        except Exception as exc:
            self._respond(500, {"error": str(exc)})

    def _respond(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
