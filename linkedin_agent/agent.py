"""
Job filter: strict $190k+ salary requirement.

Two modes:
  - With ANTHROPIC_API_KEY set: Claude does smart filtering + adds highlights.
  - Without key (default): pure Python regex extracts salary figures and filters >= $190k.

Either way, only jobs with an explicit salary >= $190k are kept.
"""
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Matches salary figures like: $190k, $200,000, $195K, 190000, $210k-$230k
_SAL_RE = re.compile(r"\$?\s*(\d[\d,]*)\s*[kK]?", re.IGNORECASE)


def _parse_salary_max(salary_str: str) -> float:
    """Return the highest salary figure mentioned, in dollars. 0 if none found."""
    if not salary_str:
        return 0.0
    best = 0.0
    for m in _SAL_RE.finditer(salary_str):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        # If the original token had 'k'/'K' or the number looks like thousands
        full_match = m.group(0)
        if re.search(r"[kK]", full_match) or val < 1000:
            val *= 1000
        best = max(best, val)
    return best


def _python_filter(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure-Python salary filter — no API key needed."""
    kept = []
    for job in jobs:
        sal = job.get("salary", "")
        if not sal:
            continue  # no salary listed → skip (strict mode)
        if _parse_salary_max(sal) >= 190_000:
            job.setdefault("highlight", "")
            kept.append(job)
    logger.info("Python filter kept %d / %d jobs (salary >= $190k)", len(kept), len(jobs))
    return kept


_SYSTEM_PROMPT = """\
You are a job search assistant for a senior product leader.

STRICT SALARY RULE:
- Keep ONLY jobs with an explicit salary >= $190,000/year.
- Discard jobs with no salary or salary < $190k.

For every KEPT job:
1. Set "salary" to the clean salary string (e.g. "$195k–$220k").
2. Set "highlight" to <=15 words on why the role is compelling.
3. Sort most compelling first.

Return ONLY a valid JSON array with fields: title, company, location, url, posted, salary, highlight.
Return [] if nothing qualifies. No text outside the JSON."""


def filter_and_enrich(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Filter to $190k+ roles and optionally enrich with Claude highlights.
    Falls back to pure-Python filtering if no API key is set.
    """
    if not jobs:
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("No ANTHROPIC_API_KEY — using Python salary filter")
        return _python_filter(jobs)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        payload = [{k: v for k, v in j.items() if k != "id"} for j in jobs]
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    "Filter to $190k+ only and add highlights:\n\n"
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
        logger.info("Claude kept %d / %d jobs", len(filtered), len(jobs))
        return filtered
    except Exception as e:
        logger.error("Claude filter failed (%s) — falling back to Python filter", e)
        return _python_filter(jobs)
