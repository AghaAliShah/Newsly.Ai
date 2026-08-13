"""SlackPosterTool: posts headline + summary + link to a Slack channel.

Gotcha: chat.postMessage returns HTTP 200 even on failure (bad token, wrong
channel, not-in-channel). The real signal is the "ok" field in the JSON
body — raise_for_status() alone would let failures pass silently.
"""

import os

from pydantic import BaseModel

from newsbot.schemas import Article
from newsbot.tools.base import BaseTool
from newsbot.tools.http import request_with_retry

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"


class SlackPostInput(BaseModel):
    headline: str
    source_url: str
    summary: str | None = None


class SlackPosterTool(BaseTool):
    name: str = "slack_poster"
    description: str = "Posts a headline + summary + link to the configured Slack channel."
    args_schema: type[SlackPostInput] = SlackPostInput

    def _run(self, headline: str, source_url: str, summary: str | None = None) -> str:
        return self._post(headline, source_url, summary)

    def post_article(self, article: Article) -> None:
        self._post(article.headline, str(article.source_url), article.summary)

    def _post(self, headline: str, source_url: str, summary: str | None, max_retries: int = 2) -> str:
        token = os.environ.get("SLACK_BOT_TOKEN")
        channel = os.environ.get("SLACK_CHANNEL_ID")
        if not token or not channel:
            raise RuntimeError("SLACK_BOT_TOKEN and SLACK_CHANNEL_ID must be set in .env.")

        text = f"*<{source_url}|{headline}>*"
        if summary:
            text += f"\n{summary}"

        payload = {"channel": channel, "text": text}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}

        response = request_with_retry(
            "POST", SLACK_POST_URL, headers=headers, json_payload=payload,
            max_retries=max_retries, service_name="Slack", timeout=10,
        )
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API returned an error: {data.get('error')}")
        return data.get("ts", "")
