"""Shared data contracts between tools.

Every tool in this pipeline speaks Article in and Article out. That's
the whole point of typing this early: NewsFetcher, Summarizer, Slack,
and Sheets all agree on one shape instead of each parsing loose strings.
"""

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class Article(BaseModel):
    headline: str
    source_url: HttpUrl
    source_name: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    summary: str | None = None  # filled in later by SummarizerTool


class NewsFetchInput(BaseModel):
    topic: str = Field(..., description="Topic to search news for, e.g. 'AI', 'crypto'")
    max_results: int = Field(10, ge=1, le=50, description="Max articles to return")
