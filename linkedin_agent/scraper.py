"""
Multi-source job scraper for Senior/Principal PM roles.

Sources:
  1. LinkedIn  — guest API (works on residential IPs; cloud IPs may get 403)
  2. Indeed    — HTML scrape (works on residential IPs)
  3. Adzuna    — REST API (requires free key; works from any IP)
  4. Remotive  — REST API (no auth; remote-only)

Recency window: past 7 days.
Salary data captured when available; Claude filters to $190k+.
"""
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TITLES = [
    "Senior Product Manager",
    "Principal Product Manager",
    "Senior Director of Product Management",
]

# 7 days in seconds
_7_DAYS = 7 * 24 * 3600


# ── LinkedIn ──────────────────────────────────────────────────────────────────

_LI_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_LI_SEARCHES = [
    {"location": "Colorado, United States", "f_WT": None},
    {"location": "United States", "f_WT": "2"},  # Remote
]


def _li_search(keywords: str, location: str, f_wt: Optional[str]) -> list[dict]:
    params: dict = {
        "keywords": keywords,
        "location": location,
        "f_TPR": f"r{_7_DAYS}",
        "start": 0,
        "count": 25,
    }
    if f_wt:
        params["f_WT"] = f_wt
    try:
        r = requests.get(f"{_LI_API}?{urlencode(params)}", headers=_HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.debug("LinkedIn failed: %s", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    jobs = []
    for card in soup.find_all("li"):
        try:
            t = card.find("h3", class_=re.compile("base-search-card__title"))
            c = card.find("h4", class_=re.compile("base-search-card__subtitle"))
            l = card.find("span", class_=re.compile("job-search-card__location"))
            a = card.find("a", class_=re.compile("base-card__full-link")) or \
                card.find("a", href=re.compile(r"/jobs/view/"))
            d = card.find("time")
            sal = card.find(class_=re.compile("job-search-card__salary-info"))
            if not (t and c and a):
                continue
            raw_url = a["href"].split("?")[0]
            m = re.search(r"/jobs/view/(\d+)", raw_url)
            jobs.append({
                "id": m.group(1) if m else raw_url,
                "source": "LinkedIn",
                "title": t.get_text(strip=True),
                "company": c.get_text(strip=True),
                "location": l.get_text(strip=True) if l else location,
                "url": raw_url,
                "posted": d.get("datetime", "") if d else "",
                "salary": sal.get_text(strip=True) if sal else "",
            })
        except Exception:
            continue
    return jobs


def scrape_linkedin() -> list[dict]:
    out, seen = [], set()
    for title in TITLES:
        for s in _LI_SEARCHES:
            for job in _li_search(title, s["location"], s.get("f_WT")):
                if job["id"] not in seen:
                    seen.add(job["id"])
                    out.append(job)
            time.sleep(1.5)
    if out:
        logger.info("LinkedIn: %d jobs", len(out))
    else:
        logger.warning("LinkedIn: 0 jobs (IP may be blocked — run from a residential IP)")
    return out


# ── Indeed ────────────────────────────────────────────────────────────────────

_INDEED_SEARCHES = [
    {"l": "Colorado"},
    {"l": "Remote"},
]


def _indeed_search(q: str, location: str) -> list[dict]:
    params = {"q": f'"{q}"', "l": location, "fromage": "7", "limit": 25}
    try:
        r = requests.get("https://www.indeed.com/jobs?" + urlencode(params),
                         headers=_HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.debug("Indeed failed: %s", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    jobs = []
    for card in soup.find_all("div", class_=re.compile("job_seen_beacon")):
        try:
            t = card.find("span", id=re.compile("jobTitle"))
            c = card.find("span", {"data-testid": "company-name"})
            loc = card.find("div", {"data-testid": "text-location"})
            a = card.find("a", id=re.compile("jobTitle"))
            sal = card.find("div", {"data-testid": "attribute_snippet_testid"})
            if not (t and a):
                continue
            href = a.get("href", "")
            full_url = f"https://www.indeed.com{href}" if href.startswith("/") else href
            jk = re.search(r"jk=([a-f0-9]+)", href)
            jobs.append({
                "id": jk.group(1) if jk else full_url,
                "source": "Indeed",
                "title": t.get_text(strip=True),
                "company": c.get_text(strip=True) if c else "",
                "location": loc.get_text(strip=True) if loc else location,
                "url": full_url,
                "posted": "",
                "salary": sal.get_text(strip=True) if sal else "",
            })
        except Exception:
            continue
    return jobs


def scrape_indeed() -> list[dict]:
    out, seen = [], set()
    for title in TITLES:
        for s in _INDEED_SEARCHES:
            for job in _indeed_search(title, s["l"]):
                if job["id"] not in seen:
                    seen.add(job["id"])
                    out.append(job)
            time.sleep(1)
    if out:
        logger.info("Indeed: %d jobs", len(out))
    else:
        logger.warning("Indeed: 0 jobs (may be blocked from this IP)")
    return out


# ── Adzuna ────────────────────────────────────────────────────────────────────

def scrape_adzuna() -> list[dict]:
    """Free tier: 100 calls/day. Sign up at https://developer.adzuna.com/"""
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []

    out, seen = [], set()
    for title in TITLES[:2]:
        for loc in ["Colorado", "Remote"]:
            params = {
                "app_id": app_id, "app_key": app_key,
                "what": title, "where": loc, "country": "us",
                "max_days_old": 7, "results_per_page": 20,
            }
            try:
                r = requests.get(
                    "https://api.adzuna.com/v1/api/jobs/us/search/1?" + urlencode(params),
                    timeout=15)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                logger.debug("Adzuna failed: %s", e)
                continue
            for job in data.get("results", []):
                jid = job.get("id", "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                sal_min = job.get("salary_min")
                sal_max = job.get("salary_max")
                salary_str = ""
                if sal_min and sal_max:
                    salary_str = f"${int(sal_min):,}–${int(sal_max):,}"
                elif sal_min:
                    salary_str = f"${int(sal_min):,}+"
                out.append({
                    "id": jid,
                    "source": "Adzuna",
                    "title": job.get("title", ""),
                    "company": job.get("company", {}).get("display_name", ""),
                    "location": job.get("location", {}).get("display_name", loc),
                    "url": job.get("redirect_url", ""),
                    "posted": job.get("created", "")[:10],
                    "salary": salary_str,
                })
            time.sleep(0.5)
    if out:
        logger.info("Adzuna: %d jobs", len(out))
    return out


# ── Remotive ──────────────────────────────────────────────────────────────────

def scrape_remotive() -> list[dict]:
    """Free REST API, remote-only jobs."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        r = requests.get(
            "https://remotive.com/api/remote-jobs?category=product&limit=100",
            headers=_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.debug("Remotive failed: %s", e)
        return []

    target = {
        "senior product manager", "principal product manager",
        "senior director of product", "vp of product", "head of product",
    }
    out = []
    for job in data.get("jobs", []):
        title_lower = job.get("title", "").lower()
        if not any(kw in title_lower for kw in target):
            continue
        pub = job.get("publication_date", "")[:10]
        try:
            pub_dt = datetime.fromisoformat(pub).replace(tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
        except (ValueError, TypeError):
            pass  # keep if we can't parse the date
        sal = job.get("salary", "")
        out.append({
            "id": str(job.get("id", "")),
            "source": "Remotive",
            "title": job.get("title", ""),
            "company": job.get("company_name", ""),
            "location": "Remote",
            "url": job.get("url", ""),
            "posted": pub,
            "salary": sal if sal else "",
        })
    if out:
        logger.info("Remotive: %d jobs", len(out))
    return out


# ── Entry point ───────────────────────────────────────────────────────────────

def scrape_jobs() -> list[dict]:
    """Scrape all sources; return deduplicated list."""
    all_jobs: list[dict] = []
    seen: set[str] = set()
    for fn in [scrape_linkedin, scrape_indeed, scrape_adzuna, scrape_remotive]:
        try:
            for job in fn():
                uid = job.get("id") or job.get("url", "")
                if uid and uid not in seen:
                    seen.add(uid)
                    all_jobs.append(job)
        except Exception as e:
            logger.error("%s failed: %s", fn.__name__, e)
    logger.info("Total unique jobs scraped: %d", len(all_jobs))
    return all_jobs
