"""Vercel serverless endpoint feeding the UI's breaking-news ticker.

GET /api/headlines -> recent AI headlines, fetch-only (no summarization).

Cached at Vercel's edge via s-maxage: the ticker runs on every page load, so
without caching each visitor would burn a Serper call. With it, the cost is
one call per 15-minute window no matter how many people open the page —
which is what makes a public, unauthenticated ticker affordable at all.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from newsbot.pipeline import fetch_headlines  # noqa: E402

CACHE_CONTROL = "public, s-maxage=900, stale-while-revalidate=3600"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            articles = fetch_headlines()
            self._respond(200, {
                "headlines": [
                    {"headline": a.headline, "source_url": str(a.source_url), "source_name": a.source_name}
                    for a in articles
                ]
            })
        except Exception as exc:
            # The ticker is decoration, not content — a failure here must not
            # look like a broken page. The UI hides the bar on a non-200.
            self._respond(503, {"error": str(exc), "headlines": []}, cache=False)

    def _respond(self, status: int, body: dict, cache: bool = True) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", CACHE_CONTROL if cache else "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
