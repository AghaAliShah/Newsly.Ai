"""Vercel endpoint for the Slack `/update <topic>` slash command.

Slack requires an ack within 3 seconds or it shows the command as failed
in the user's client, but the actual pipeline run (fetch -> summarize ->
post to Slack -> log to Sheet) routinely takes much longer than that. So
this handler never runs the pipeline inline: it verifies the request
really came from Slack (see slack_security.py), fires a fire-and-forget
call to /api/run-topic — a separate serverless invocation that does the
real work and posts its own results directly to Slack/Sheets — and acks
immediately. Closing our end of that request early doesn't cancel the
target invocation; Vercel's Lambda-backed functions run to completion
regardless of whether the caller is still listening.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from newsbot.slack_security import verify_slack_signature  # noqa: E402

MAX_TOPIC_LEN = 100


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length else b""

        signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
        if not signing_secret or not verify_slack_signature(
            signing_secret,
            self.headers.get("X-Slack-Request-Timestamp", ""),
            raw_body,
            self.headers.get("X-Slack-Signature", ""),
        ):
            self._respond(401, {"error": "invalid signature"})
            return

        topic = (parse_qs(raw_body.decode()).get("text") or [""])[0].strip()

        if not topic:
            self._slack_ack("Usage: `/update <topic>` — e.g. `/update AI`")
            return
        if len(topic) > MAX_TOPIC_LEN:
            self._slack_ack(f"Topic is too long (max {MAX_TOPIC_LEN} chars).")
            return

        self._trigger_run(topic)
        self._slack_ack(f"Running the news pipeline for *{topic}*… results will post here and log to the Sheet shortly.")

    def _trigger_run(self, topic: str) -> None:
        base_url = f"https://{self.headers.get('Host', '')}"
        try:
            requests.get(
                f"{base_url}/api/run-topic",
                params={"topic": topic},
                headers={"Authorization": f"Bearer {os.environ.get('CRON_SECRET', '')}"},
                timeout=0.3,
            )
        except requests.exceptions.RequestException:
            pass  # expected: we intentionally don't wait for the run to finish

    def _slack_ack(self, text: str) -> None:
        self._respond(200, {"response_type": "in_channel", "text": text})

    def _respond(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
