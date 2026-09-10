# Jira Worklog Dashboard

Team tool to generate **shareable HTML dashboards** from Jira worklogs — daily progress, charts by person name, and day-wise ticket breakdown.

Works with any Jira Cloud instance. Built for Sarathi (`the-nudge.atlassian.net`) but configurable via `config.json`.

## Quick start

```bash
git clone <this-repo-url>
cd jira-worklog-dashboard

cp config.example.json config.json
python3 -m pip install -r requirements.txt
```

Edit `config.json`:

| Field | Example |
|---|---|
| `base_url` | `https://the-nudge.atlassian.net` |
| `email` | your Atlassian account email |
| `api_token` | from [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `default_author` | your Jira display name |
| `project_key` | `SARATHI` (optional) |

**Never commit `config.json`.** Each teammate keeps their own local copy.

## Generate a dashboard

```bash
# Your own worklog — opens in browser
python3 generate_dashboard.py --serve

# Specific person
python3 generate_dashboard.py --author "Ayushi Mittal" --serve

# Full team (everyone who logged time this month)
python3 generate_dashboard.py --team --serve

# Convenience wrapper
chmod +x run_daily.sh
./run_daily.sh
./run_daily.sh 2026-09 "Ayushi Mittal"
```

Output: `output/worklog-dashboard-YYYY-MM.html`

Share the HTML file on Slack, email, or Confluence. Recipients can view it in any browser without Jira access.

## What you get

- **Person selector** — switch between teammates (team mode)
- **Daily hours chart** — bar chart per day
- **Ticket chart** — doughnut chart by Jira key
- **Day-wise tables** — issue, description, start/end time, duration
- **Monthly summary** — total hours, avg/day, unusual days

Working days: Monday–Friday.

## Team workflow

| When | Who | Command |
|---|---|---|
| Before standup | Each person | `./run_daily.sh` |
| Weekly review | Tech lead | `python3 generate_dashboard.py --team --serve` |
| Share report | Anyone | Attach `output/worklog-dashboard-*.html` to Slack |

## Cursor users

If you use Cursor with Atlassian MCP connected, run:

```
/worklog-dashboard
/worklog-dashboard team
```

See `.cursor/commands/worklog-dashboard.md`.

## CLI reference

```
--month YYYY-MM     Month to report (default: current)
--author NAME       Filter by display name or email
--authors A,B,C     Comma-separated names
--team              All authors with worklogs
--project KEY       Jira project filter
--serve             Open in browser after generation
--output PATH       Custom output path
```

## Troubleshooting

| Issue | Fix |
|---|---|
| `401 Unauthorized` | Check email + API token in `config.json` |
| Empty dashboard | Author name must match Jira display name exactly |
| Missing hours | Script paginates full worklogs per issue (not limited to 20) |

## Project layout

```
jira-worklog-dashboard/
├── generate_dashboard.py      # Main script
├── dashboard_template.html    # Shareable HTML UI
├── config.example.json        # Config template
├── run_daily.sh               # Daily wrapper
├── requirements.txt
├── output/                    # Generated reports (gitignored)
└── .cursor/commands/          # Optional Cursor agent command
```

## License

Internal team use. Do not commit API tokens or generated reports with sensitive data.
