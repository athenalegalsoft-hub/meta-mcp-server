"""FastMCP server for Meta Marketing API campaign management.

Environment:
  META_ACCESS_TOKEN: Meta access token with ads_read / ads_management permissions.
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any, Literal

from dotenv import load_dotenv
from fastmcp import FastMCP
from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.user import User

load_dotenv()

mcp = FastMCP("meta-marketing-api")

VALID_PRESETS = {"last_7_days", "last_30_days", "last_90_days"}
VALID_STATUSES = {"ACTIVE", "PAUSED"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _require_token() -> str:
    token = os.getenv("META_ACCESS_TOKEN")
    if not token:
        raise ValueError(
            "META_ACCESS_TOKEN is not set. Add it as an environment variable before starting the server."
        )
    return token


def _init_api() -> None:
    FacebookAdsApi.init(access_token=_require_token())


def _normalize_ad_account_id(ad_account_id: str) -> str:
    if not ad_account_id or not isinstance(ad_account_id, str):
        raise ValueError("ad_account_id is required.")
    cleaned = ad_account_id.strip()
    if not cleaned.startswith("act_"):
        cleaned = f"act_{cleaned}"
    if not re.fullmatch(r"act_\d+", cleaned):
        raise ValueError("ad_account_id must be a Meta ad account ID, e.g. act_123456789 or 123456789.")
    return cleaned


def _validate_date(value: str, field_name: str) -> str:
    if not value or not DATE_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid date in YYYY-MM-DD format.") from exc
    return value


def _time_params(
    date_range: str = "last_7_days",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    if start_date or end_date:
        if not start_date or not end_date:
            raise ValueError("Both start_date and end_date are required for a custom range.")
        since = _validate_date(start_date, "start_date")
        until = _validate_date(end_date, "end_date")
        if since > until:
            raise ValueError("start_date must be earlier than or equal to end_date.")
        return {"time_range": {"since": since, "until": until}}

    if date_range not in VALID_PRESETS:
        raise ValueError("date_range must be one of: last_7_days, last_30_days, last_90_days.")
    return {"date_preset": date_range}


def _extract_leads(actions: list[dict[str, Any]] | None) -> float | None:
    if not actions:
        return None
    lead_action_types = {
        "lead",
        "onsite_conversion.lead_grouped",
        "onsite_conversion.lead",
        "offsite_conversion.fb_pixel_lead",
    }
    total = 0.0
    found = False
    for action in actions:
        if action.get("action_type") in lead_action_types:
            found = True
            try:
                total += float(action.get("value", 0) or 0)
            except (TypeError, ValueError):
                continue
    return total if found else None


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _format_error(exc: Exception) -> str:
    if isinstance(exc, FacebookRequestError):
        code = exc.api_error_code()
        subcode = exc.api_error_subcode()
        message = exc.api_error_message() or str(exc)
        lowered = message.lower()
        if code in {4, 17, 32, 613} or "rate" in lowered or "too many" in lowered:
            return f"Meta API rate limit reached. Please wait and retry. Details: {message}"
        if code in {190, 102} or "token" in lowered or "oauth" in lowered:
            return f"Meta access token is invalid, expired, or missing required permissions. Details: {message}"
        return f"Meta API error: {message} (code={code}, subcode={subcode})"
    return str(exc)


def _error_response(exc: Exception) -> dict[str, Any]:
    return {"ok": False, "error": _format_error(exc)}


@mcp.tool()
def list_ad_accounts() -> dict[str, Any]:
    """List all Meta ad accounts available to META_ACCESS_TOKEN."""
    try:
        _init_api()
        accounts = User("me").get_ad_accounts(
            fields=[
                AdAccount.Field.account_id,
                AdAccount.Field.name,
                AdAccount.Field.currency,
                AdAccount.Field.timezone_name,
            ]
        )
        return {
            "ok": True,
            "ad_accounts": [
                {
                    "account_id": account.get("account_id"),
                    "account_name": account.get("name"),
                    "currency": account.get("currency"),
                    "timezone": account.get("timezone_name"),
                }
                for account in accounts
            ],
        }
    except Exception as exc:  # noqa: BLE001 - MCP tools should return structured errors.
        return _error_response(exc)


@mcp.tool()
def get_campaign_performance(
    ad_account_id: str,
    date_range: Literal["last_7_days", "last_30_days", "last_90_days"] = "last_7_days",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Return campaign-level spend, traffic, lead, CPL, CPC, and CTR metrics."""
    try:
        _init_api()
        account = AdAccount(_normalize_ad_account_id(ad_account_id))
        params = {
            "level": "campaign",
            "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions",
            **_time_params(date_range, start_date, end_date),
        }
        insights = account.get_insights(params=params)

        campaigns = []
        for row in insights:
            spend = _safe_float(row.get("spend"))
            impressions = _safe_int(row.get("impressions"))
            clicks = _safe_int(row.get("clicks"))
            leads = _extract_leads(row.get("actions"))
            cpl = round(spend / leads, 2) if leads and leads > 0 else None
            cpc = round(spend / clicks, 2) if clicks > 0 else None
            ctr = round((clicks / impressions) * 100, 2) if impressions > 0 else None
            campaigns.append(
                {
                    "campaign_id": row.get("campaign_id"),
                    "campaign_name": row.get("campaign_name"),
                    "spend": round(spend, 2),
                    "impressions": impressions,
                    "clicks": clicks,
                    "leads": leads,
                    "cpl": cpl,
                    "cpc": cpc,
                    "ctr": ctr,
                }
            )

        return {"ok": True, "campaigns": campaigns, "leads_note": "leads is null when Meta does not return lead action data."}
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc)


@mcp.tool()
def get_campaign_details(campaign_id: str) -> dict[str, Any]:
    """Get status, objective, budget, and schedule details for a campaign."""
    try:
        if not campaign_id or not str(campaign_id).strip().isdigit():
            raise ValueError("campaign_id must be a numeric Meta campaign ID.")
        _init_api()
        campaign = Campaign(str(campaign_id).strip()).api_get(
            fields=[
                Campaign.Field.name,
                Campaign.Field.status,
                Campaign.Field.objective,
                Campaign.Field.daily_budget,
                Campaign.Field.lifetime_budget,
                Campaign.Field.start_time,
                Campaign.Field.stop_time,
            ]
        )
        return {
            "ok": True,
            "campaign": {
                "campaign_id": campaign_id,
                "campaign_name": campaign.get("name"),
                "status": campaign.get("status"),
                "objective": campaign.get("objective"),
                "daily_budget": campaign.get("daily_budget"),
                "lifetime_budget": campaign.get("lifetime_budget"),
                "start_time": campaign.get("start_time"),
                "end_time": campaign.get("stop_time"),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc)


@mcp.tool()
def update_campaign_status(campaign_id: str, status: Literal["ACTIVE", "PAUSED"]) -> dict[str, Any]:
    """Update a Meta campaign status to ACTIVE or PAUSED."""
    try:
        if not campaign_id or not str(campaign_id).strip().isdigit():
            raise ValueError("campaign_id must be a numeric Meta campaign ID.")
        normalized_status = status.upper().strip()
        if normalized_status not in VALID_STATUSES:
            raise ValueError("status must be ACTIVE or PAUSED.")
        _init_api()
        Campaign(str(campaign_id).strip()).api_update(params={"status": normalized_status})
        return {
            "ok": True,
            "message": f"Campaign {campaign_id} status updated to {normalized_status}.",
            "campaign_id": campaign_id,
            "status": normalized_status,
        }
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc)


@mcp.tool()
def get_lead_forms(ad_account_id: str) -> dict[str, Any]:
    """List lead generation forms for a Meta ad account."""
    try:
        _init_api()
        account = AdAccount(_normalize_ad_account_id(ad_account_id))
        forms = account.get_lead_gen_forms(fields=["id", "name", "status"])
        return {
            "ok": True,
            "lead_forms": [
                {
                    "form_id": form.get("id"),
                    "form_name": form.get("name"),
                    "status": form.get("status"),
                }
                for form in forms
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc)


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
