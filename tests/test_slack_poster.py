from unittest.mock import Mock, patch

import pytest

from newsbot.schemas import Article
from newsbot.tools.slack_poster import SlackPosterTool

SLACK_ENV = {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_CHANNEL_ID": "C123"}


@patch.dict("os.environ", SLACK_ENV)
@patch("newsbot.tools.http.requests.request")
def test_post_article_success(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = {"ok": True, "ts": "1690000000.000100"}
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    article = Article(
        headline="AI model beats benchmark",
        source_url="https://example.com/a",
        summary="A new model set a record.",
    )
    tool = SlackPosterTool()
    tool.post_article(article)  # no exception = success

    sent_payload = mock_post.call_args.kwargs["json"]
    assert "example.com/a" in sent_payload["text"]
    assert "A new model set a record." in sent_payload["text"]


@patch.dict("os.environ", SLACK_ENV)
@patch("newsbot.tools.http.requests.request")
def test_post_article_raises_on_api_level_error(mock_post):
    # HTTP 200 but Slack-level failure — must not be treated as success.
    mock_response = Mock()
    mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    article = Article(headline="X", source_url="https://example.com/x")
    tool = SlackPosterTool()
    with pytest.raises(RuntimeError, match="channel_not_found"):
        tool.post_article(article)


@patch.dict("os.environ", {}, clear=True)
def test_post_requires_credentials():
    tool = SlackPosterTool()
    with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
        tool._post("headline", "https://example.com", None)
