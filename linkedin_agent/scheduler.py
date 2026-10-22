"""
Every-3-days scheduler (long-running process alternative to cron).

Usage:
    python linkedin_agent/scheduler.py
    RUN_AT=09:00 python linkedin_agent/scheduler.py

Or use cron (no long-running process needed):
    0 13 */3 * *  cd /path/to/jobtracker && python3 linkedin_agent/run.py >> /home/user/job_alert.log 2>&1
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

import schedule
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from run import run_once

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RUN_AT = os.environ.get("RUN_AT", "07:00")


def _safe_run() -> None:
    try:
        run_once()
    except Exception as e:
        logger.error("run_once() failed: %s", e, exc_info=True)


if __name__ == "__main__":
    logger.info("Scheduler started — every 3 days at %s", RUN_AT)
    schedule.every(3).days.at(RUN_AT).do(_safe_run)

    logger.info("Running immediately on first start…")
    _safe_run()

    while True:
        schedule.run_pending()
        time.sleep(60)
