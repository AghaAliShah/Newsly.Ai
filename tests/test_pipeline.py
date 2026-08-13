from unittest.mock import Mock, patch

from newsbot.pipeline import run_pipeline
from newsbot.schemas import Article

ARTICLE_A = Article(headline="Story A", source_url="https://example.com/a")
ARTICLE_B = Article(headline="Story B", source_url="https://example.com/b")
ARTICLE_C = Article(headline="Story C (already logged)", source_url="https://example.com/c")


@patch("newsbot.pipeline.SheetsLoggerTool")
@patch("newsbot.pipeline.SlackPosterTool")
@patch("newsbot.pipeline.SummarizerTool")
@patch("newsbot.pipeline.NewsFetcherTool")
def test_pipeline_skips_already_logged_and_isolates_failures(
    mock_fetcher_cls, mock_summarizer_cls, mock_poster_cls, mock_sheets_cls
):
    mock_fetcher = Mock()
    mock_fetcher._fetch.return_value = [ARTICLE_A, ARTICLE_B, ARTICLE_C]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_sheets = Mock()
    mock_sheets.get_logged_urls.return_value = {"https://example.com/c"}
    mock_sheets_cls.return_value = mock_sheets

    def summarize_side_effect(article):
        if article.headline == "Story B":
            raise RuntimeError("Groq timed out")
        return article.model_copy(update={"summary": f"Summary of {article.headline}"})

    mock_summarizer = Mock()
    mock_summarizer.summarize.side_effect = summarize_side_effect
    mock_summarizer_cls.return_value = mock_summarizer

    mock_poster_cls.return_value = Mock()

    result = run_pipeline(topic="AI", max_results=10)

    assert result.skipped_duplicates == 1  # Story C, already in the sheet
    assert [a.headline for a in result.posted] == ["Story A"]
    assert result.failed == ["Story B"]
    mock_sheets.log_article.assert_called_once()
