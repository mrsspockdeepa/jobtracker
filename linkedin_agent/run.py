"""
One-shot runner: scrape -> filter -> email.

Usage:
    python linkedin_agent/run.py           # live run
    python linkedin_agent/run.py --test    # mock email (no scraping) to verify setup
"""
import logging
import os
import sys

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from scraper import scrape_jobs
from agent import filter_and_enrich
from emailer import send_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_MOCK = [
    {
        "title": "Principal Product Manager — AI Platform",
        "company": "Google",
        "location": "Remote",
        "url": "https://www.linkedin.com/jobs/view/111111",
        "posted": "2026-10-20",
        "salary": "$210,000–$240,000",
        "highlight": "Lead AI infrastructure product strategy at Google scale",
    },
    {
        "title": "Senior Product Manager — Commerce",
        "company": "Ibotta",
        "location": "Denver, CO",
        "url": "https://www.linkedin.com/jobs/view/222222",
        "posted": "2026-10-19",
        "salary": "$195,000–$215,000",
        "highlight": "Denver fintech unicorn, high-growth loyalty platform",
    },
    {
        "title": "Senior Director of Product",
        "company": "Palantir",
        "location": "Denver, CO (Hybrid)",
        "url": "https://www.linkedin.com/jobs/view/333333",
        "posted": "2026-10-18",
        "salary": "$200,000–$230,000",
        "highlight": "Define product vision for government data platform",
    },
]


def _check_env() -> list[str]:
    return [v for v in ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"] if not os.environ.get(v)]


def run_once(test_mode: bool = False) -> None:
    missing = _check_env()
    if missing:
        logger.error("Missing env vars: %s", ", ".join(missing))
        logger.error("Copy linkedin_agent/.env.example → linkedin_agent/.env and fill in values.")
        sys.exit(1)

    if test_mode:
        logger.info("=== TEST MODE — mock data, no live scraping ===")
        jobs = _MOCK
    else:
        logger.info("=== PM Job Alert Agent starting ===")
        logger.info("Step 1/3 — Scraping…")
        raw = scrape_jobs()
        logger.info("Scraped %d unique listings", len(raw))

        logger.info("Step 2/3 — Filtering to $190k+ with Claude…")
        jobs = filter_and_enrich(raw)
        logger.info("%d jobs after salary filter", len(jobs))

    logger.info("Step 3/3 — Sending email…")
    send_digest(jobs)
    logger.info("=== Done ===")


if __name__ == "__main__":
    run_once(test_mode="--test" in sys.argv)
