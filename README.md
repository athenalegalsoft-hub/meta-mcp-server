# Meta Marketing API MCP Server

A FastMCP server that lets Claude read Meta campaign performance data and manage Meta ad campaigns through the Meta Marketing API.

## Tools exposed

- `list_ad_accounts` — Lists ad accounts available to the access token.
- `get_campaign_performance` — Returns campaign spend, impressions, clicks, leads, CPL, CPC, and CTR.
- `get_campaign_details` — Returns campaign name, status, objective, budgets, and schedule.
- `update_campaign_status` — Updates a campaign to `ACTIVE` or `PAUSED`.
- `get_lead_forms` — Lists Meta lead forms for an ad account.

## Requirements

- Python 3.10+
- Meta access token with the right permissions, usually:
  - `ads_read` for read-only tools
  - `ads_management` for `update_campaign_status`
  - business/ad account access for the ad accounts you want to manage

## Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Set `META_ACCESS_TOKEN`

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
META_ACCESS_TOKEN=your_real_meta_access_token
```

Do not commit `.env` to source control.

You can also set it directly in your shell:

```bash
export META_ACCESS_TOKEN="your_real_meta_access_token"
```

## Run locally for testing

```bash
python server.py
```

The server starts an HTTP MCP endpoint on:

```text
http://localhost:8000/mcp
```

If your host injects a `PORT` environment variable, the server automatically uses it.

## Deploy to Render free tier

1. Create a new GitHub repository with these files:
   - `server.py`
   - `requirements.txt`
   - `.env.example`
   - `README.md`
2. Push the repository to GitHub.
3. In Render, choose **New → Web Service**.
4. Connect the GitHub repository.
5. Use these settings:
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python server.py`
   - **Instance Type:** Free
6. In **Environment**, add:
   - Key: `META_ACCESS_TOKEN`
   - Value: your real Meta access token
7. Deploy.

Render will provide a public URL like:

```text
https://your-service-name.onrender.com
```

Your MCP endpoint should be:

```text
https://your-service-name.onrender.com/mcp
```

## Connect to Claude.ai

1. Open Claude.ai.
2. Go to MCP connector settings.
3. Add a new custom connector.
4. Use your Render MCP URL:

```text
https://your-service-name.onrender.com/mcp
```

5. Save and enable the connector.

Then ask Claude questions such as:

- “Show me last week’s campaign performance.”
- “List the ad accounts I can access.”
- “Pause campaign 12345.”
- “What is the CPL for the last 30 days?”

## Notes on Meta API behavior

- Lead counts are based on the `actions` array returned by Meta Insights. If Meta does not return lead actions, `leads` and `cpl` are returned as `null`.
- Budgets from Meta are often returned in the smallest currency unit, depending on the account currency.
- Rate limits, invalid/expired tokens, and permission errors are returned as structured MCP tool responses with `ok: false`.

## Local smoke test with MCP Inspector

You can test the HTTP MCP server with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

Use this endpoint:

```text
http://localhost:8000/mcp
```
