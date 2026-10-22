"""
Gmail SMTP emailer for the job alert digest.
Sends HTML + plain-text via SSL on port 465.
"""
import logging
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;background:#f5f3ff;color:#1e1b4b;margin:0;padding:0}}
.wrap{{max-width:640px;margin:32px auto;background:#fff;border-radius:16px;
       box-shadow:0 4px 24px rgba(109,93,160,.12);overflow:hidden}}
.hdr{{background:linear-gradient(135deg,#7c3aed,#ec4899);padding:28px 32px;color:#fff}}
.hdr h1{{margin:0;font-size:22px;font-weight:700}}
.hdr p{{margin:6px 0 0;font-size:13px;opacity:.85}}
.body{{padding:24px 32px}}
.count{{font-size:13px;color:#6b7280;margin-bottom:20px}}
.job{{border:1px solid #ede9fe;border-radius:12px;padding:16px 18px;margin-bottom:14px}}
.job-title{{font-size:15px;font-weight:600;margin-bottom:3px}}
.job-title a{{color:#7c3aed;text-decoration:none}}
.job-title a:hover{{text-decoration:underline}}
.job-meta{{font-size:12px;color:#6b7280;margin-bottom:6px}}
.sal{{display:inline-block;background:#ecfdf5;color:#065f46;font-size:11px;
      font-weight:700;padding:3px 8px;border-radius:20px;margin-right:6px}}
.hl{{font-size:12px;background:#f5f3ff;color:#5b21b6;
     padding:5px 10px;border-radius:6px;display:inline-block;margin-top:5px}}
.empty{{text-align:center;padding:40px;color:#9ca3af;font-size:14px}}
.ftr{{background:#f9fafb;padding:14px 32px;text-align:center;
      font-size:11px;color:#9ca3af;border-top:1px solid #ede9fe}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>&#128188; PM Job Alert</h1>
    <p>Senior &amp; Principal PM · $190k+ · Colorado + Remote · {date}</p>
  </div>
  <div class="body">
    <p class="count"><strong>{count}</strong> role{plural} found in the past 7 days</p>
    {cards}
  </div>
  <div class="ftr">Sent every 3 days · Roles sourced from LinkedIn, Indeed, Adzuna &amp; Remotive</div>
</div>
</body>
</html>"""

_CARD = """\
<div class="job">
  <div class="job-title"><a href="{url}" target="_blank">{title}</a></div>
  <div class="job-meta">{company} &nbsp;·&nbsp; {location}{posted_str}</div>
  {sal_badge}{hl_badge}
</div>"""

_EMPTY = """\
<div class="empty">
  No roles with explicit $190k+ salary were found in the past 7 days.<br/>
  Check back in 3 days!
</div>"""


def _render_html(jobs: list[dict[str, Any]]) -> str:
    today = date.today().strftime("%B %d, %Y")
    count = len(jobs)
    plural = "s" if count != 1 else ""

    if not jobs:
        cards_html = _EMPTY
    else:
        parts = []
        for j in jobs:
            posted_str = f" &nbsp;·&nbsp; {j['posted']}" if j.get("posted") else ""
            sal = j.get("salary", "").strip()
            sal_badge = f'<span class="sal">&#128176; {sal}</span>' if sal else ""
            hl = j.get("highlight", "").strip()
            hl_badge = f'<div class="hl">&#10024; {hl}</div>' if hl else ""
            parts.append(_CARD.format(
                url=j.get("url", "#"),
                title=j.get("title", ""),
                company=j.get("company", ""),
                location=j.get("location", ""),
                posted_str=posted_str,
                sal_badge=sal_badge,
                hl_badge=hl_badge,
            ))
        cards_html = "\n".join(parts)

    return _HTML.format(date=today, count=count, plural=plural, cards=cards_html)


def send_digest(jobs: list[dict[str, Any]]) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", sender)

    today = date.today().strftime("%b %d, %Y")
    subject = (
        f"[Job Alert] {len(jobs)} PM role{'s' if len(jobs) != 1 else ''} "
        f"$190k+ · {today}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"PM Job Alert <{sender}>"
    msg["To"] = recipient

    plain = [f"PM Job Alert — {today}", f"{len(jobs)} role(s) with $190k+ salary\n"]
    for j in jobs:
        plain.append(
            f"• {j.get('title')} @ {j.get('company')} "
            f"({j.get('location')}) — {j.get('salary','')}"
        )
        plain.append(f"  {j.get('url', '')}\n")
    msg.attach(MIMEText("\n".join(plain), "plain"))
    msg.attach(MIMEText(_render_html(jobs), "html"))

    logger.info("Sending digest → %s (%d jobs)…", recipient, len(jobs))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(sender, password)
        srv.sendmail(sender, recipient, msg.as_string())
    logger.info("Email sent.")
