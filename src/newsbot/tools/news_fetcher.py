"""NewsFetcherTool: pulls recent news for a topic via the Serper.dev News API.

Design choices worth noticing (this is the "beyond vibe coding" part):

1. Input/output are validated Pydantic models, not raw dicts — a malformed
   API response fails loudly at the boundary instead of silently corrupting
   whatever runs downstream (Summarizer, Slack, Sheets).
2. One bad article doesn't kill the batch: we validate each result
   individually and skip+log failures rather than let one bad `date` field
   raise and lose all 10 headlines.
3. Dedup by source_url. This tool will run on a schedule; the same
   breaking story often reappears across calls. Downstream idempotency
   starts here, not in the Sheets logger.
4. A real timeout and a small bounded retry. Without a timeout, a hung
   Serper request hangs your whole cron job.
"""

import logging
import os

from newsbot.schemas import Article, NewsFetchInput
from newsbot.tools.base import BaseTool
from newsbot.tools.http import request_with_retry

logger = logging.getLogger(__name__)

SERPER_NEWS_URL = "https://google.serper.dev/news"


class NewsFetcherTool(BaseTool):
    name: str = "news_fetcher"
    description: str = (
        "Fetches recent news articles for a given topic. "
        "Input: topic (str), max_results (int, default 10). "
        "Returns a JSON list of articles with headline, source_url, snippet, published_at."
    )
    args_schema: type[NewsFetchInput] = NewsFetchInput

    def _run(self, topic: str, max_results: int = 10) -> str:
        articles = self._fetch(topic, max_results)
        return "[" + ", ".join(a.model_dump_json() for a in articles) + "]"

    def _fetch(self, topic: str, max_results: int, max_retries: int = 2) -> list[Article]:
        api_key = os.environ.get("SERPER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "SERPER_API_KEY is not set. Add it to your .env file "
                "(get one free at https://serper.dev)."
            )

        payload = {"q": topic, "num": max_results}
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

        response = request_with_retry(
            "POST", SERPER_NEWS_URL, headers=headers, json_payload=payload,
            max_retries=max_retries, service_name="Serper", timeout=10,
        )
        raw_results = response.json().get("news", [])
        return self._to_articles(raw_results, max_results)

    @staticmethod
    def _to_articles(raw_results: list[dict], max_results: int) -> list[Article]:
        seen_urls: set[str] = set()
        articles: list[Article] = []

        for item in raw_results:
            try:
                article = Article(
                    headline=item["title"],
                    source_url=item["link"],
                    source_name=item.get("source"),
                    snippet=item.get("snippet"),
                    published_at=None,  # Serper's "date" is a relative string like "2 hours ago" — not parsed here
                )
            except Exception as exc:
                logger.warning("Skipping malformed article %r: %s", item, exc)
                continue

            url_str = str(article.source_url)
            if url_str in seen_urls:
                continue
            seen_urls.add(url_str)
            articles.append(article)

            if len(articles) >= max_results:
                break

        return articles
