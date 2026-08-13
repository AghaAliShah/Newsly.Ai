"""Orchestrates NewsFetcher -> Summarizer -> SlackPoster -> SheetsLogger.

Plain function calls, not a crewai Crew: this pipeline is a fixed sequence
decided in advance, not a case where an LLM needs to choose which tool to
call next. An agent framework buys you nothing here but dependency weight
and an extra layer between you and the stack trace when something breaks.
"""

import logging
import time

from pydantic import BaseModel

from newsbot.schemas import Article
from newsbot.tools.news_fetcher import NewsFetcherTool
from newsbot.tools.sheets_logger import SheetsLoggerTool
from newsbot.tools.slack_poster import SlackPosterTool
from newsbot.tools.summarizer import SummarizerTool

logger = logging.getLogger(__name__)


class PipelineResult(BaseModel):
    topic: str
    posted: list[Article]
    failed: list[str]  # headlines that errored partway through, kept as strings for JSON-friendliness
    skipped_duplicates: int


def run_pipeline(topic: str, max_results: int = 10) -> PipelineResult:
    fetcher = NewsFetcherTool()
    summarizer = SummarizerTool()
    poster = SlackPosterTool()
    sheets = SheetsLoggerTool()

    # Fetch/auth failures here are systemic (bad key, network down) — let them raise,
    # don't swallow them into a "0 articles processed" result that looks like success.
    already_logged = sheets.get_logged_urls()
    articles = fetcher._fetch(topic, max_results)

    new_articles = [a for a in articles if str(a.source_url) not in already_logged]
    skipped = len(articles) - len(new_articles)

    posted: list[Article] = []
    failed: list[str] = []
    for i, article in enumerate(new_articles):
        if i > 0:
            time.sleep(2)  # spread requests out — free-tier OpenRouter rate-limits a tight burst
        try:
            summarized = summarizer.summarize(article)
            poster.post_article(summarized)
            sheets.log_article(summarized)
            posted.append(summarized)
        except Exception:
            logger.exception("Failed to process article: %s", article.headline)
            failed.append(article.headline)

    return PipelineResult(topic=topic, posted=posted, failed=failed, skipped_duplicates=skipped)


def fetch_headlines(topic: str = "AI", max_results: int = 12) -> list[Article]:
    """Headlines only — no summarizer, no Slack, no Sheets. Feeds the UI's
    breaking-news ticker, which needs to be cheap and fast enough to run on
    every page load: skipping the LLM turns a ~15s multi-call job into one
    Serper request. The endpoint in front of this caches at the CDN, so the
    ticker costs roughly one API call per cache window, not one per visitor.
    """
    return NewsFetcherTool()._fetch(topic, max_results)


def search_topic(topic: str, max_results: int = 6) -> tuple[list[Article], int]:
    """Fetch + summarize on demand for the interactive UI. No Slack post, no Sheets log,
    no dedup-by-history — a search is a one-off look-up, not part of the logged record.
    max_results defaults low (6, vs. 10 for the cron pipeline) to keep this fast enough
    for a live web request instead of the 6-hourly job's more relaxed budget.
    """
    fetcher = NewsFetcherTool()
    summarizer = SummarizerTool()

    articles = fetcher._fetch(topic, max_results)

    results: list[Article] = []
    failures = 0
    consecutive_failures = 0

    for i, article in enumerate(articles):
        # Once the summarizer has failed twice in a row it is almost never a
        # bad article — it's the LLM being down, out of quota, or rate-limited,
        # and every further call just burns retries and backoff against a wall.
        # Stop calling and hand back the rest unsummarized: a headline with a
        # working link still has value, and this keeps the request inside the
        # serverless time budget instead of timing out with nothing to show.
        if consecutive_failures >= 2:
            results.append(article)
            failures += 1
            continue

        if i > 0:
            time.sleep(1)
        try:
            results.append(summarizer.summarize(article))
            consecutive_failures = 0
        except Exception:
            logger.exception("Failed to summarize: %s", article.headline)
            failures += 1
            consecutive_failures += 1
            # Keep the article. Losing the headline entirely because the
            # summary step failed turns a partial outage into an empty page.
            results.append(article)

    return results, failures
