# Worklog Dashboard: Daily Jira Progress Report

**Input**: optional text — e.g. `Ayushi Mittal`, `team`, or comma-separated names

## Objective

Generate a shareable HTML worklog dashboard for the current month. Write output to `output/worklog-dashboard-YYYY-MM.html` in this repo.

## Process

1. Parse scope: empty = current MCP user; `team` = all authors; name(s) = filter
2. Query Jira via Atlassian MCP (read-only) for worklogs in the current month
3. Build day-wise model: date, issue key, summary, start/end time, hours per ticket
4. Embed data into `dashboard_template.html` (replace `__DASHBOARD_DATA__`)
5. Write HTML to `output/` and share the file path with the user

Working days = Monday–Friday.

Do not create or modify Jira worklogs.

## Alternative

If MCP unavailable but `config.json` exists:

```bash
python3 generate_dashboard.py --author "NAME" --serve
```
