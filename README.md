# Jira Worklog Dashboard

Team tool to generate **shareable HTML dashboards** from Jira worklogs — daily progress, charts by person name, and day-wise ticket breakdown.

Works with any Jira Cloud instance. Preconfigured for Sarathi (`the-nudge.atlassian.net`) via `config.json`.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.9+** | Check with `python3 --version` |
| **pip** | Usually bundled with Python |
| **Jira Cloud access** | Account on your Atlassian site |
| **Jira API token** | One per person — see [Setup step 3](#3-create-your-jira-api-token) |
| **Git** | To clone this repo |

Optional:

- **Cursor IDE** with Atlassian MCP — run `/worklog-dashboard` without an API token
- **Browser** — to view generated HTML reports

---

## Setup

Follow these steps once per machine (each teammate does this independently).

### 1. Get the code

**Option A — clone from remote (recommended for team)**

```bash
git clone <this-repo-url>
cd jira-worklog-dashboard
```

**Option B — already on your machine**

```bash
cd /path/to/jira-worklog-dashboard
```

**Option C — open in Cursor**

1. **File → Open Folder**
2. Select the `jira-worklog-dashboard` folder
3. (Optional) Connect Atlassian MCP in Cursor settings for agent-based runs

---

### 2. Install Python dependencies

```bash
python3 -m pip install -r requirements.txt
```

Verify:

```bash
python3 -c "import requests; print('OK')"
```

Expected output: `OK`

---

### 3. Create your Jira API token

1. Log in to [Atlassian account settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Label it e.g. `worklog-dashboard`
4. Copy the token immediately — it is shown only once

Use the **same email** you use to log in to Jira (`the-nudge.atlassian.net`).

---

### 4. Create your local config

```bash
cp config.example.json config.json
```

Edit `config.json` with your values:

```json
{
  "base_url": "https://the-nudge.atlassian.net",
  "email": "your.name@company.com",
  "api_token": "paste-your-api-token-here",
  "default_author": "Your Jira Display Name",
  "project_key": "SARATHI"
}
```

| Field | What to put |
|---|---|
| `base_url` | Your Jira site URL (no trailing slash) |
| `email` | Atlassian account email |
| `api_token` | Token from step 3 |
| `default_author` | **Exact** Jira display name (Profile → name shown on worklogs) |
| `project_key` | Optional filter, e.g. `SARATHI` |

> **Important:** `config.json` is gitignored. Never commit it or share it in Slack.

**Find your Jira display name:** open any worklog you created in Jira — the author name shown there is what goes in `default_author`.

---

### 5. Verify setup

Run a quick test (generates HTML without opening browser):

```bash
python3 generate_dashboard.py --month $(date +%Y-%m)
```

Check:

- No `401 Unauthorized` error
- File created at `output/worklog-dashboard-YYYY-MM.html`
- Console prints your name under `People:`

Open the HTML file in a browser to confirm charts and day-wise tables load.

---

## Run

### Daily personal dashboard (most common)

```bash
chmod +x run_daily.sh   # once only
./run_daily.sh
```

This will:

1. Use the current month
2. Use `default_author` from your `config.json`
3. Write `output/worklog-dashboard-YYYY-MM.html`
4. Open the report in your default browser

---

### Run with options

**Specific month**

```bash
./run_daily.sh 2026-09
python3 generate_dashboard.py --month 2026-09 --serve
```

**Specific person (must match Jira display name)**

```bash
./run_daily.sh 2026-09 "Ayushi Mittal"
python3 generate_dashboard.py --author "Ayushi Mittal" --serve
```

**Full team — everyone who logged time this month**

```bash
python3 generate_dashboard.py --team --serve
```

**Named teammates only**

```bash
python3 generate_dashboard.py --authors "Ayushi Mittal,Abhay Singh" --serve
```

**Generate without opening browser**

```bash
python3 generate_dashboard.py
```

**Custom output path**

```bash
python3 generate_dashboard.py --output ~/Desktop/my-worklog.html --serve
```

---

### Share the report

After each run, share this file with your team:

```
output/worklog-dashboard-YYYY-MM.html
```

| Channel | How |
|---|---|
| Slack | Drag-and-drop the HTML file into a channel |
| Email | Attach the file |
| Confluence | Upload as attachment |
| Local | Double-click to open in browser |

The HTML is self-contained — recipients do not need Python or Jira access to **view** the report (only to click through to tickets).

---

### Cursor agent (no API token)

If Atlassian MCP is connected in Cursor, open this repo and run:

```
/worklog-dashboard
/worklog-dashboard Ayushi Mittal
/worklog-dashboard team
```

The agent queries Jira and writes to `output/worklog-dashboard-YYYY-MM.html`.

---

## What you get

- **Person selector** — switch between teammates (team mode)
- **Daily hours chart** — bar chart per day
- **Ticket chart** — doughnut chart by Jira key
- **Day-wise tables** — issue, description, start/end time, duration
- **Monthly summary** — total hours, avg/day, ticket count, unusual days

Working days: **Monday–Friday**.

---

## Team workflow

| When | Who | Command |
|---|---|---|
| Before standup | Each person | `./run_daily.sh` |
| Weekly review | Tech lead | `python3 generate_dashboard.py --team --serve` |
| Share report | Anyone | Attach `output/worklog-dashboard-*.html` to Slack |

---

## CLI reference

```bash
python3 generate_dashboard.py [options]

  --month YYYY-MM       Month to report (default: current month)
  --author NAME         Filter by Jira display name or email
  --authors A,B,C       Comma-separated names
  --team                Include everyone who logged time
  --project KEY         Jira project key filter (overrides config)
  --output PATH         Custom output HTML path
  --serve               Open in browser after generation
  --port 8765           Port used with --serve (default: 8765)
  --config PATH         Custom config file path
```

**`run_daily.sh` shorthand**

```bash
./run_daily.sh                          # current month, default author, --serve
./run_daily.sh 2026-09                  # specific month
./run_daily.sh 2026-09 "Ayushi Mittal"  # specific month + author
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `Config not found` | Run `cp config.example.json config.json` and fill in values |
| `401 Unauthorized` | Re-check `email` and `api_token` in `config.json` |
| `Missing dependency: requests` | Run `python3 -m pip install -r requirements.txt` |
| Empty dashboard / no people | `default_author` must match Jira display name exactly |
| Wrong person's data | Use `--author "Exact Display Name"` |
| Missing worklog hours | Script paginates all worklogs per issue (not limited to 20) |
| Browser does not open | Open `output/worklog-dashboard-*.html` manually |
| Permission denied on `run_daily.sh` | Run `chmod +x run_daily.sh` |

---

## Project layout

```
jira-worklog-dashboard/
├── generate_dashboard.py      # Main script — fetches Jira, builds HTML
├── dashboard_template.html    # Shareable dashboard UI template
├── config.example.json        # Config template (copy to config.json)
├── config.json                # Your local secrets (gitignored — create this)
├── run_daily.sh               # Daily wrapper script
├── requirements.txt           # Python dependencies
├── output/                    # Generated HTML reports (gitignored)
└── .cursor/commands/          # Cursor agent command (/worklog-dashboard)
```

---

## License

Internal team use. Do not commit API tokens or generated reports containing sensitive data.
