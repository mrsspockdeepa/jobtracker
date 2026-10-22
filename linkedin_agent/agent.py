"""
Claude-powered job filter.

Strict rule: keep ONLY roles that explicitly list a salary >= $190k.
Roles with no salary listed or salary < $190k are discarded.
Each kept job gets a one-line 'highlight' and a clean 'salary' label.
"""
import json
import logging
import os
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a job search assistant for a senior product leader looking for their next role.

STRICT SALARY RULE:
- Keep a job ONLY if it explicitly states a salary, base pay, or total comp >= $190,000/year.
  Examples of qualifying salary text: "$195k", "$200,000–$230,000", "up to $220k", "TC $210k+".
- Discard any job that lists NO salary information.
- Discard any job whose listed salary is below $190,000/year.

For every job you KEEP:
1. Set "salary" to the cleaned salary range string (e.g. "$195k–$220k").
2. Set "highlight" to <=15 words: what makes this role compelling (company, domain, scope).
3. Sort most compelling first.

Return ONLY a valid JSON array. Each element must have exactly these fields:
  title, company, location, url, posted, salary, highlight

Return [] if nothing qualifies. No text outside the JSON array."""


def filter_and_enrich(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use Claude to strictly filter to $190k+ roles and add highlights."""
    if not jobs:
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Claude filter, returning raw jobs")
        for job in jobs:
            job.setdefault("highlight", "")
            job.setdefault("salary", job.get("salary", ""))
        return jobs

    client = anthropic.Anthropic(api_key=api_key)
    payload = [{k: v for k, v in j.items() if k != "id"} for j in jobs]

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    "Filter these job listings to only those with explicit salary >= $190k.\n\n"
                    + json.dumps(payload, indent=2)
                ),
            }],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        filtered: list[dict] = json.loads(raw)
        logger.info("Claude kept %d / %d jobs (salary >= $190k)", len(filtered), len(jobs))
        return filtered
    except (anthropic.APIError, json.JSONDecodeError, IndexError) as e:
        logger.error("Claude filter failed (%s) — falling back to raw list", e)
        for job in jobs:
            job.setdefault("highlight", "")
        return jobs
