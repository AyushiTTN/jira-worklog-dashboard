#!/usr/bin/env python3
"""Generate a shareable HTML Jira worklog dashboard for individuals or teams.

Usage:
  python generate_dashboard.py --author "Ayushi Mittal"
  python generate_dashboard.py --team --authors "Ayushi Mittal,Abhay Singh"
  python generate_dashboard.py --month 2026-09 --serve

Requires credentials/jira-api.json (see config.example.json).
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "config.json"
EXAMPLE_CONFIG = SCRIPT_DIR / "config.example.json"
OUTPUT_DIR = SCRIPT_DIR / "output"
WORKING_DAYS = {0, 1, 2, 3, 4}


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(
            f"Config not found: {path}\nCopy {EXAMPLE_CONFIG.name} to config.json and fill in values.",
            file=sys.stderr,
        )
        sys.exit(1)
    with path.open() as f:
        return json.load(f)


def parse_jira_datetime(value: str) -> datetime:
    if value.endswith("+0530"):
        value = value[:-5] + "+05:30"
    return datetime.fromisoformat(value)


def fmt_duration(seconds: int) -> str:
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/") + "/"
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = self.session.get(url, params=params, timeout=60)
        response.raise_for_status()
        return response.json()

    def search_issues(self, jql: str, fields: list[str]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        start_at = 0
        while True:
            payload = self._get(
                "rest/api/3/search",
                {
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": 100,
                    "fields": ",".join(fields),
                },
            )
            issues.extend(payload.get("issues", []))
            start_at += payload.get("maxResults", 100)
            total = payload.get("total", 0)
            if start_at >= total:
                break
        return issues

    def fetch_issue_worklogs(self, issue_id: str) -> list[dict[str, Any]]:
        worklogs: list[dict[str, Any]] = []
        start_at = 0
        while True:
            payload = self._get(
                f"rest/api/3/issue/{issue_id}/worklog",
                {"startAt": start_at, "maxResults": 100},
            )
            worklogs.extend(payload.get("worklogs", []))
            total = payload.get("total", 0)
            start_at += payload.get("maxResults", 100)
            if start_at >= total:
                break
        return worklogs


def month_bounds(month: str) -> tuple[datetime, datetime, str, str]:
    year, mon = map(int, month.split("-"))
    start = datetime(year, mon, 1)
    last_day = calendar.monthrange(year, mon)[1]
    end = datetime(year, mon, last_day, 23, 59, 59)
    return start, end, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def author_matches(worklog: dict[str, Any], author_filter: str | None) -> bool:
    if not author_filter:
        return True
    author = worklog.get("author", {})
    needle = author_filter.strip().lower()
    return needle in (
        author.get("displayName", "").lower(),
        author.get("emailAddress", "").lower(),
        author.get("accountId", "").lower(),
    )


def collect_worklogs(
    client: JiraClient,
    month: str,
    author_filter: str | None,
    project_key: str | None,
) -> list[dict[str, Any]]:
    start, end, start_str, end_str = month_bounds(month)
    jql_parts = [
        f'worklogDate >= "{start_str}"',
        f'worklogDate <= "{end_str}"',
    ]
    if author_filter:
        jql_parts.append(f'worklogAuthor ~ "{author_filter}"')
    if project_key:
        jql_parts.append(f'project = "{project_key}"')
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"

    issues = client.search_issues(jql, ["summary", "issuetype", "project"])
    entries: list[dict[str, Any]] = []

    for issue in issues:
        key = issue["key"]
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        issue_type = fields.get("issuetype", {}).get("name", "")
        project = fields.get("project", {}).get("key", "")
        for wl in client.fetch_issue_worklogs(issue["id"]):
            if not author_matches(wl, author_filter):
                continue
            started = parse_jira_datetime(wl["started"])
            started_naive = started.replace(tzinfo=None)
            if not (start <= started_naive <= end):
                continue
            seconds = int(wl.get("timeSpentSeconds", 0))
            ended = started + timedelta(seconds=seconds)
            author = wl.get("author", {})
            entries.append(
                {
                    "date": started.strftime("%Y-%m-%d"),
                    "day": started.strftime("%A"),
                    "author": author.get("displayName", "Unknown"),
                    "accountId": author.get("accountId", ""),
                    "key": key,
                    "summary": summary,
                    "type": issue_type,
                    "project": project,
                    "startTime": fmt_time(started),
                    "endTime": fmt_time(ended),
                    "seconds": seconds,
                    "duration": fmt_duration(seconds),
                    "hours": round(seconds / 3600, 2),
                }
            )

    entries.sort(key=lambda item: (item["date"], item["author"], item["startTime"]))
    return entries


def build_dashboard_model(
    entries: list[dict[str, Any]],
    month: str,
    authors: list[str] | None,
) -> dict[str, Any]:
    start, end, _, _ = month_bounds(month)
    month_label = start.strftime("%B %Y")

    by_author: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        by_author[entry["author"]].append(entry)

    people = []
    for author_name in sorted(by_author.keys()):
        author_entries = by_author[author_name]
        by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_issue: dict[str, int] = defaultdict(int)
        issue_summaries: dict[str, str] = {}

        for entry in author_entries:
            by_date[entry["date"]].append(entry)
            by_issue[entry["key"]] += entry["seconds"]
            issue_summaries[entry["key"]] = entry["summary"]

        days = []
        for date in sorted(by_date.keys()):
            day_entries = by_date[date]
            dt = datetime.strptime(date, "%Y-%m-%d")
            ticket_totals: dict[str, int] = defaultdict(int)
            for entry in day_entries:
                ticket_totals[entry["key"]] += entry["seconds"]
            day_seconds = sum(entry["seconds"] for entry in day_entries)
            days.append(
                {
                    "date": date,
                    "dateDisplay": dt.strftime("%d %b %Y"),
                    "day": dt.strftime("%A"),
                    "isWorkingDay": dt.weekday() in WORKING_DAYS,
                    "totalSeconds": day_seconds,
                    "totalFormatted": fmt_duration(day_seconds),
                    "totalHours": round(day_seconds / 3600, 2),
                    "entries": day_entries,
                    "ticketTotals": [
                        {
                            "key": key,
                            "formatted": fmt_duration(seconds),
                            "hours": round(seconds / 3600, 2),
                        }
                        for key, seconds in sorted(ticket_totals.items(), key=lambda item: -item[1])
                    ],
                }
            )

        total_seconds = sum(entry["seconds"] for entry in author_entries)
        working_days = [day for day in days if day["isWorkingDay"]]
        avg_hours = round(
            sum(day["totalHours"] for day in working_days) / max(len(working_days), 1),
            2,
        )

        issue_summary = [
            {
                "key": key,
                "summary": issue_summaries[key][:100],
                "formatted": fmt_duration(seconds),
                "hours": round(seconds / 3600, 2),
            }
            for key, seconds in sorted(by_issue.items(), key=lambda item: -item[1])
        ]

        anomalies = []
        if working_days:
            threshold_low = avg_hours * 0.6
            threshold_high = avg_hours * 1.2
            for day in working_days:
                if day["totalHours"] < threshold_low:
                    anomalies.append(
                        {
                            "date": day["dateDisplay"],
                            "type": "low",
                            "hours": day["totalFormatted"],
                        }
                    )
                elif day["totalHours"] > threshold_high:
                    anomalies.append(
                        {
                            "date": day["dateDisplay"],
                            "type": "high",
                            "hours": day["totalFormatted"],
                        }
                    )

        people.append(
            {
                "name": author_name,
                "totalFormatted": fmt_duration(total_seconds),
                "totalHours": round(total_seconds / 3600, 2),
                "workingDaysLogged": len(working_days),
                "averageHours": avg_hours,
                "averageFormatted": fmt_duration(int(avg_hours * 3600)),
                "ticketCount": len(by_issue),
                "entryCount": len(author_entries),
                "dailyChart": {
                    "labels": [day["dateDisplay"].replace(f" {start.year}", "") for day in days],
                    "hours": [day["totalHours"] for day in days],
                },
                "issueChart": {
                    "labels": [item["key"] for item in issue_summary[:8]],
                    "hours": [item["hours"] for item in issue_summary[:8]],
                },
                "days": days,
                "issueSummary": issue_summary,
                "anomalies": anomalies,
            }
        )

    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "month": month,
        "monthLabel": month_label,
        "jiraBaseUrl": "",
        "selectedAuthors": authors or [person["name"] for person in people],
        "people": people,
    }


def render_html(model: dict[str, Any], jira_base_url: str) -> str:
    model = dict(model)
    model["jiraBaseUrl"] = jira_base_url.rstrip("/")
    payload = json.dumps(model)
    template_path = SCRIPT_DIR / "dashboard_template.html"
    template = template_path.read_text(encoding="utf-8")
    return template.replace("__DASHBOARD_DATA__", payload)


def serve_file(path: Path, port: int) -> None:
    directory = str(path.parent)
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=directory, **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/{path.name}"
    print(f"Serving dashboard at {url}")
    print("Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate shareable Jira worklog dashboard HTML")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to config.json")
    parser.add_argument("--month", default=datetime.now().strftime("%Y-%m"), help="Month as YYYY-MM")
    parser.add_argument("--author", help="Filter by display name or email")
    parser.add_argument("--authors", help="Comma-separated names for team mode")
    parser.add_argument("--team", action="store_true", help="Include all authors found in the month")
    parser.add_argument("--project", help="Optional Jira project key, e.g. SARATHI")
    parser.add_argument("--output", type=Path, help="Output HTML path")
    parser.add_argument("--serve", action="store_true", help="Open dashboard in local browser")
    parser.add_argument("--port", type=int, default=8765, help="Port for --serve")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    client = JiraClient(
        config["base_url"],
        config["email"],
        config["api_token"],
    )

    author_filters: list[str | None]
    if args.team:
        author_filters = [None]
    elif args.authors:
        author_filters = [name.strip() for name in args.authors.split(",") if name.strip()]
    elif args.author:
        author_filters = [args.author]
    else:
        author_filters = [config.get("default_author")]

    entries: list[dict[str, Any]] = []
    for author_filter in author_filters:
        entries.extend(
            collect_worklogs(
                client,
                args.month,
                author_filter,
                args.project or config.get("project_key"),
            )
        )

    # Deduplicate identical worklog rows if multiple author filters overlap
    seen = set()
    unique_entries = []
    for entry in entries:
        key = (
            entry["accountId"],
            entry["key"],
            entry["date"],
            entry["startTime"],
            entry["seconds"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique_entries.append(entry)

    selected_authors = None if args.team else author_filters
    model = build_dashboard_model(unique_entries, args.month, selected_authors)  # type: ignore[arg-type]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or OUTPUT_DIR / f"worklog-dashboard-{args.month}.html"
    output_path.write_text(render_html(model, config["base_url"]), encoding="utf-8")

    print(f"Generated: {output_path}")
    print(f"People: {', '.join(person['name'] for person in model['people']) or 'none'}")
    print(f"Share this file with teammates — it works offline in any browser.")

    if args.serve:
        serve_file(output_path, args.port)


if __name__ == "__main__":
    main()
