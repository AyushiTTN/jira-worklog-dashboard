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
import socket
import sys
import webbrowser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
# from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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
    # if not path.exists():
    #     print(
    #         f"Config not found: {path}\nCopy {EXAMPLE_CONFIG.name} to config.json and fill in values.",
    #         file=sys.stderr,
    #     )
    #     sys.exit(1)
    # with path.open() as f:
    #     return json.load(f)
    config: dict[str, Any] = {}
    if path.exists():
        with path.open() as f:
            config = json.load(f)
    env_map = {
        "base_url": "JIRA_BASE_URL",
        "email": "JIRA_EMAIL",
        "api_token": "JIRA_API_TOKEN",
        "default_author": "JIRA_DEFAULT_AUTHOR",
        "project_key": "JIRA_PROJECT_KEY",
    }
    for key, env_name in env_map.items():
        value = os.environ.get(env_name)
        if value:
            config[key] = value
    required = ("base_url", "email", "api_token")
    if not all(config.get(item) for item in required):
        print(
            f"Config not found: {path}\n"
            f"Copy {EXAMPLE_CONFIG.name} to config.json, or set "
            "JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(1)
    return config


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

    def _post(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = self.session.post(url, json=json_body, timeout=60)
        response.raise_for_status()
        return response.json()

    def search_issues(self, jql: str, fields: list[str]) -> list[dict[str, Any]]:
        # GET /rest/api/3/search was removed (HTTP 410). Use /search/jql with
        # cursor pagination instead of startAt/total.
        # issues: list[dict[str, Any]] = []
        # start_at = 0
        # while True:
        #     payload = self._get(
        #         "rest/api/3/search",
        #         {
        #             "jql": jql,
        #             "startAt": start_at,
        #             "maxResults": 100,
        #             "fields": ",".join(fields),
        #         },
        #     )
        #     issues.extend(payload.get("issues", []))
        #     start_at += payload.get("maxResults", 100)
        #     total = payload.get("total", 0)
        #     if start_at >= total:
        #         break
        # return issues
        issues: list[dict[str, Any]] = []
        next_page_token: str | None = None
        while True:
            body: dict[str, Any] = {
                "jql": jql,
                "maxResults": 100,
                "fields": fields,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            payload = self._post("rest/api/3/search/jql", body)
            issues.extend(payload.get("issues", []))
            next_page_token = payload.get("nextPageToken")
            if payload.get("isLast", not next_page_token) or not next_page_token:
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


def recent_months(now: datetime | None = None, count: int = 3) -> list[dict[str, str]]:
    """Current month plus the previous two months."""
    current = now or datetime.now()
    year, month = current.year, current.month
    months: list[dict[str, str]] = []
    for _ in range(count):
        start = datetime(year, month, 1)
        months.append(
            {
                "value": start.strftime("%Y-%m"),
                "label": start.strftime("%B %Y"),
            }
        )
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return months


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
        # Fuzzy ~ matches nobody for display names on this site.
        # jql_parts.append(f'worklogAuthor ~ "{author_filter}"')
        jql_parts.append(f'worklogAuthor = "{author_filter}"')
    if project_key:
        jql_parts.append(f'project = "{project_key}"')
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"

    # issues = client.search_issues(jql, ["summary", "issuetype", "project"])
    issues = client.search_issues(
        jql,
        ["summary", "issuetype", "project", "worklog"],
    )
    entries: list[dict[str, Any]] = []

    # for issue in issues:
    #     ...
    #     for wl in client.fetch_issue_worklogs(issue["id"]):
    def process_issue(issue: dict[str, Any]) -> list[dict[str, Any]]:
        issue_entries: list[dict[str, Any]] = []
        key = issue["key"]
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        issue_type = fields.get("issuetype", {}).get("name", "")
        project = fields.get("project", {}).get("key", "")
        embedded_worklogs = fields.get("worklog", {})
        worklogs = embedded_worklogs.get("worklogs", [])
        if embedded_worklogs.get("total", 0) > len(worklogs):
            worklogs = client.fetch_issue_worklogs(issue["id"])
        for wl in worklogs:
            if not author_matches(wl, author_filter):
                continue
            started = parse_jira_datetime(wl["started"])
            started_naive = started.replace(tzinfo=None)
            if not (start <= started_naive <= end):
                continue
            seconds = int(wl.get("timeSpentSeconds", 0))
            ended = started + timedelta(seconds=seconds)
            author = wl.get("author", {})
            issue_entries.append(
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
        return issue_entries

    with ThreadPoolExecutor(max_workers=10) as executor:
        for issue_entries in executor.map(process_issue, issues):
            entries.extend(issue_entries)

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
    for author_name in sorted(by_author.keys(), key=str.casefold):
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


def lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def serve_file(
    path: Path,
    port: int,
    refresh_dashboard: Any,
) -> None:
    directory = str(path.parent)
    # handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(  # noqa: E731
    #     *args, directory=directory, **kwargs
    # )
    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *handler_args: Any, **handler_kwargs: Any):
            super().__init__(
                *handler_args,
                directory=directory,
                **handler_kwargs,
            )

        def do_POST(self) -> None:
            if self.path != "/refresh":
                self.send_error(404)
                return
            try:
                # model = refresh_dashboard()
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw.decode("utf-8") or "{}") if raw else {}
                model = refresh_dashboard(body.get("month"))
                payload = json.dumps(model).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                payload = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self.path = f"/{path.name}"
            super().do_GET()

    handler = DashboardHandler
    # server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    # url = f"http://127.0.0.1:{port}/{path.name}"
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    local_url = f"http://127.0.0.1:{port}/{path.name}"
    team_url = f"http://{lan_ip()}:{port}/{path.name}"
    print(f"Serving dashboard at {local_url}", flush=True)
    print(f"Team URL (same Wi-Fi/VPN): {team_url}", flush=True)
    print("Keep this process running. Press Ctrl+C to stop.", flush=True)
    # webbrowser.open(local_url)
    if not os.environ.get("RENDER"):
        webbrowser.open(local_url)
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
    # parser.add_argument("--port", type=int, default=8765, help="Port for --serve")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8765")),
        help="Port for --serve (Render sets PORT)",
    )
    return parser.parse_args()


def generate_dashboard(
    args: argparse.Namespace,
    config: dict[str, Any],
    month: str | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    selected_month = month or args.month
    allowed = {item["value"] for item in recent_months()}
    if month and selected_month not in allowed:
        raise ValueError("Month must be the current month or one of the previous two months.")

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
        # author_filters = [config.get("default_author") or "Ayushi Mittal"]
        author_filters = [None]

    entries: list[dict[str, Any]] = []
    for author_filter in author_filters:
        entries.extend(
            collect_worklogs(
                client,
                # args.month,
                selected_month,
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

    # selected_authors = None if args.team else author_filters
    selected_authors = None if author_filters == [None] else author_filters
    # model = build_dashboard_model(unique_entries, args.month, selected_authors)  # type: ignore[arg-type]
    model = build_dashboard_model(unique_entries, selected_month, selected_authors)  # type: ignore[arg-type]
    model["defaultPerson"] = config.get("default_author") or "Ayushi Mittal"
    model["availableMonths"] = recent_months()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # output_path = args.output or OUTPUT_DIR / f"worklog-dashboard-{args.month}.html"
    html_path = output_path or args.output or OUTPUT_DIR / f"worklog-dashboard-{selected_month}.html"
    html_path.write_text(render_html(model, config["base_url"]), encoding="utf-8")

    print(f"Generated: {html_path}")
    print(f"People: {', '.join(person['name'] for person in model['people']) or 'none'}")
    print(f"Share this file with teammates — it works offline in any browser.")
    return model


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    model = generate_dashboard(args, config)

    if args.serve:
        # serve_file(output_path, args.port)
        output_path = args.output or OUTPUT_DIR / f"worklog-dashboard-{args.month}.html"
        # serve_file(
        #     output_path,
        #     args.port,
        #     lambda: generate_dashboard(args, config),
        # )
        serve_file(
            output_path,
            args.port,
            lambda selected=None: generate_dashboard(
                args,
                config,
                month=selected,
                output_path=output_path,
            ),
        )


if __name__ == "__main__":
    main()
