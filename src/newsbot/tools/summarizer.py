"""SummarizerTool: condenses headline+snippet into 1-2 clear sentences via OpenRouter.

Caveat worth knowing: Serper gives us a short snippet, not the full article
body, so this rephrases/tightens the snippet rather than summarizing a full
article. Fixing that for real means fetching+parsing the source page
(extra dependency, extra failure surface) — deliberately out of scope here.
"""

import os

from pydantic import BaseModel

from newsbot.schemas import Article
from newsbot.tools.base import BaseTool
from newsbot.tools.http import request_with_retry

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
# Overridable via OPENROUTER_MODEL env var — free-tier slugs rotate often,
# check https://openrouter.ai/api/v1/models for what's currently free.
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it:free"  # non-reasoning: answers directly, no thinking step to run out of budget


class SummarizeInput(BaseModel):
    headline: str
    snippet: str | None = None


class SummarizerTool(BaseTool):
    name: str = "summarizer"
    description: str = "Summarizes a news headline + snippet into 1-2 clear sentences."
    args_schema: type[SummarizeInput] = SummarizeInput

    def _run(self, headline: str, snippet: str | None = None) -> str:
        return self._call_openrouter(headline, snippet)

    def summarize(self, article: Article) -> Article:
        summary = self._call_openrouter(article.headline, article.snippet)
        return article.model_copy(update={"summary": summary})

    def _call_openrouter(self, headline: str, snippet: str | None, max_retries: int = 2) -> str:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to your .env file.")
        model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

        prompt = (
            "Rewrite this news item as one clear, neutral sentence (max 30 words). "
            "No preamble, just the sentence.\n\n"
            f"Headline: {headline}\n"
            f"Snippet: {snippet or '(none provided)'}"
        )
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200,
            "reasoning": {"enabled": False},  # hard-off: "effort: low" wasn't enough, model still burned 400+ tokens thinking
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Identifies the app to OpenRouter (shows up in their dashboard/leaderboard) — optional but polite.
            "HTTP-Referer": "https://github.com/newsbot",
            "X-Title": "AI News Bot",
        }

        response = request_with_retry(
            "POST", OPENROUTER_CHAT_URL, headers=headers, json_payload=payload,
            max_retries=max_retries, service_name="OpenRouter",
        )
        choice = response.json()["choices"][0]
        content = choice["message"]["content"]
        if not content:
            # "length" here means the model spent its whole token budget on internal
            # reasoning and got cut off before writing the actual answer.
            raise RuntimeError(
                f"OpenRouter returned an empty completion "
                f"(finish_reason={choice.get('finish_reason')}): {response.text}"
            )
        return content.strip()
