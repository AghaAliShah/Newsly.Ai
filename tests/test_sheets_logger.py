import json
from unittest.mock import Mock, patch

from newsbot.schemas import Article
from newsbot.tools.sheets_logger import SheetsLoggerTool

FAKE_SERVICE_ACCOUNT = json.dumps({"type": "service_account", "project_id": "test"})
SHEETS_ENV = {
    "GOOGLE_SHEETS_CREDENTIALS_JSON": FAKE_SERVICE_ACCOUNT,
    "GOOGLE_SHEET_ID": "sheet123",
}


@patch.dict("os.environ", SHEETS_ENV)
@patch("newsbot.tools.http.requests.request")
@patch("newsbot.tools.sheets_logger.Credentials.from_service_account_info")
def test_log_article_appends_expected_row(mock_from_info, mock_post):
    mock_creds = Mock()
    mock_creds.token = "fake-access-token"
    mock_creds.refresh = Mock()
    mock_from_info.return_value = mock_creds

    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    article = Article(
        headline="AI model beats benchmark",
        source_url="https://example.com/a",
        summary="A new model set a record.",
    )
    tool = SheetsLoggerTool()
    tool.log_article(article)

    call = mock_post.call_args
    assert call.args[0] == "POST"
    assert "sheet123" in call.args[1]
    row = call.kwargs["json"]["values"][0]
    assert row[1] == "AI model beats benchmark"
    assert row[2] == "A new model set a record."
    assert row[3] == "https://example.com/a"
    assert call.kwargs["headers"]["Authorization"] == "Bearer fake-access-token"


@patch.dict("os.environ", {"GOOGLE_SHEET_ID": "sheet123"}, clear=True)
def test_log_article_requires_credentials_env():
    tool = SheetsLoggerTool()
    article = Article(headline="X", source_url="https://example.com/x")
    try:
        tool.log_article(article)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "GOOGLE_SHEETS_CREDENTIALS_JSON" in str(exc)


@patch.dict("os.environ", {}, clear=True)
def test_log_article_requires_sheet_id_env():
    tool = SheetsLoggerTool()
    article = Article(headline="X", source_url="https://example.com/x")
    try:
        tool.log_article(article)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "GOOGLE_SHEET_ID" in str(exc)
