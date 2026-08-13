from unittest.mock import Mock, patch

import pytest

from newsbot.schemas import Article
from newsbot.tools.summarizer import SummarizerTool

OPENROUTER_RESPONSE = {"choices": [{"message": {"content": "AI model beats prior benchmark by 12%."}}]}


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
@patch("newsbot.tools.http.requests.request")
def test_summarize_returns_article_with_summary(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = OPENROUTER_RESPONSE
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    article = Article(headline="AI model beats benchmark", source_url="https://example.com/a")
    tool = SummarizerTool()
    result = tool.summarize(article)

    assert result.summary == "AI model beats prior benchmark by 12%."
    assert result.headline == article.headline  # original fields untouched


@patch.dict("os.environ", {}, clear=True)
def test_summarize_requires_api_key():
    tool = SummarizerTool()
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        tool._call_openrouter("headline", "snippet")


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
@patch("newsbot.tools.http.requests.request")
def test_summarize_raises_clear_error_on_empty_completion(mock_post):
    # HTTP 200 but content is None — seen from free-tier shared-pool models under load.
    mock_response = Mock()
    mock_response.json.return_value = {"choices": [{"message": {"content": None}}]}
    mock_response.text = '{"choices": [{"message": {"content": null}}]}'
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    tool = SummarizerTool()
    with pytest.raises(RuntimeError, match="empty completion"):
        tool._call_openrouter("headline", "snippet")
