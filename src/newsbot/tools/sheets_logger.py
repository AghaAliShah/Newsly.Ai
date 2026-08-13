"""SheetsLoggerTool: appends article rows to a Google Sheet.

Uses google-auth directly (service-account JWT -> access token) plus a raw
REST call to the Sheets API, instead of google-api-python-client — that
package adds httplib2/google-api-core/protobuf for what's one HTTP call
once you already hold a bearer token.

Appending itself has no concept of "already logged" — Sheets has no unique
constraint. get_logged_urls() lets the pipeline read existing rows first
and skip anything already there, which is what actually makes reruns
(e.g. the 6-hourly cron) idempotent across runs, not just within one.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.service_account import Credentials
from pydantic import BaseModel

from newsbot.schemas import Article
from newsbot.tools.base import BaseTool
from newsbot.tools.http import request_with_retry

SHEETS_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
APPEND_URL_TEMPLATE = (
    "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{range_}:append"
)


class SheetsLogInput(BaseModel):
    headline: str
    source_url: str
    summary: str | None = None


class SheetsLoggerTool(BaseTool):
    name: str = "sheets_logger"
    description: str = "Appends a Date/Headline/Summary/Source URL row to the configured Google Sheet."
    args_schema: type[SheetsLogInput] = SheetsLogInput

    def _run(self, headline: str, source_url: str, summary: str | None = None) -> str:
        article = Article(headline=headline, source_url=source_url, summary=summary)
        self.log_article(article)
        return "logged"

    def log_article(self, article: Article) -> None:
        self._append_row(article)

    def get_logged_urls(self) -> set[str]:
        sheet_id = self._get_sheet_id()
        token = self._get_access_token()
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/Sheet1!D2:D"
        headers = {"Authorization": f"Bearer {token}"}
        response = request_with_retry("GET", url, headers=headers, service_name="Sheets", timeout=10)
        rows = response.json().get("values", [])
        return {row[0] for row in rows if row}

    def _load_credentials(self) -> Credentials:
        raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
        if not raw:
            raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS_JSON is not set in .env.")

        try:
            info = json.loads(raw)  # Vercel: env var holds the JSON content directly
        except json.JSONDecodeError:
            path = Path(raw)  # local dev: env var holds a path to the keyfile
            if not path.exists():
                raise RuntimeError(f"GOOGLE_SHEETS_CREDENTIALS_JSON is not valid JSON or a real path: {raw}")
            info = json.loads(path.read_text())

        return Credentials.from_service_account_info(info, scopes=SHEETS_SCOPE)

    def _get_sheet_id(self) -> str:
        sheet_id = os.environ.get("GOOGLE_SHEET_ID")
        if not sheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID is not set in .env.")
        return sheet_id.strip().strip("/")  # trailing slash is an easy copy-paste mistake from the sheet URL

    def _get_access_token(self) -> str:
        credentials = self._load_credentials()
        credentials.refresh(GoogleAuthRequest())
        return credentials.token

    def _append_row(self, article: Article, max_retries: int = 2) -> None:
        sheet_id = self._get_sheet_id()
        token = self._get_access_token()
        row = [
            datetime.now(timezone.utc).isoformat(),
            article.headline,
            article.summary or "",
            str(article.source_url),
        ]
        url = APPEND_URL_TEMPLATE.format(sheet_id=sheet_id, range_="Sheet1!A:D")
        headers = {"Authorization": f"Bearer {token}"}
        request_with_retry(
            "POST", url, headers=headers, json_payload={"values": [row]},
            params={"valueInputOption": "RAW"}, max_retries=max_retries,
            service_name="Sheets", timeout=10,
        )
