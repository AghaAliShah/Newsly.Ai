"""Local runner: `python -m newsbot.main AI` — no Vercel/cron needed to test."""

import logging
import sys

from dotenv import load_dotenv

from newsbot.pipeline import run_pipeline

if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI"
    result = run_pipeline(topic)
    print(result.model_dump_json(indent=2))
