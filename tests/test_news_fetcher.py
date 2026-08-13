from unittest.mock import Mock, patch

import pytest

from newsbot.tools.news_fetcher import NewsFetcherTool

SAMPLE_RESPONSE = {
    "news": [
        {
            "title": "AI model beats benchmark",
            "link": "https://example.com/a",
            "snippet": "Some snippet",
            "source": "Example News",
        },
        {
            # duplicate URL — should be deduped
            "title": "AI model beats benchmark (syndicated)",
            "link": "https://example.com/a",
            "snippet": "Same story, different outlet",
            "source": "Copy News",
        },
        {
            # missing required "link" — should be skipped, not crash the batch
            "title": "Malformed entry",
            "snippet": "no link field",
        },
        {
            "title": "Second real story",
            "link": "https://example.com/b",
            "snippet": "Another snippet",
            "source": "Example News",
        },
    ]
}


@patch.dict("os.environ", {"SERPER_API_KEY": "test-key"})
@patch("newsbot.tools.http.requests.request")
def test_fetch_dedupes_and_skips_malformed(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    tool = NewsFetcherTool()
    articles = tool._fetch(topic="AI", max_results=10)

    assert len(articles) == 2
    assert {str(a.source_url) for a in articles} == {
        "https://example.com/a",
        "https://example.com/b",
    }


@patch.dict("os.environ", {"SERPER_API_KEY": "test-key"})
@patch("newsbot.tools.http.requests.request")
def test_fetch_respects_max_results(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    tool = NewsFetcherTool()
    articles = tool._fetch(topic="AI", max_results=1)

    assert len(articles) == 1


@patch.dict("os.environ", {}, clear=True)
def test_fetch_requires_api_key():
    tool = NewsFetcherTool()
    with pytest.raises(RuntimeError, match="SERPER_API_KEY"):
        tool._fetch(topic="AI", max_results=5)
