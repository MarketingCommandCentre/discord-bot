"""
Posting-date helpers.

Each request type should be submitted a minimum amount of time before its target
date (posting date / date needed / event date). This module provides a per-type
lead-time check and a warning embed shown in the request channel when a request
is made on short notice. It never blocks a request — it only warns.
"""

from datetime import datetime

# Minimum lead time (in days) required before the target date, per request type.
DEFAULT_LEAD_DAYS = 14
LEAD_DAYS_BY_TYPE = {
    "post": 14,        # 2 weeks
    "reel": 14,        # 2 weeks
    "misc": 21,        # 3 weeks
    "website": 3,      # 3 days
    "photography": 3,  # 3 days
}

# How the target date is referred to in the warning message, per type.
DATE_NOUN_BY_TYPE = {
    "post": "posting date",
    "reel": "posting date",
    "misc": "date you need it by",
    "website": "date you need it by",
    "photography": "event date",
}


def _type_key(request_type) -> str:
    """Accept a RequestType enum or a plain string and return its string value."""
    return getattr(request_type, "value", request_type)


def _as_date(value):
    """Return a date from a date or datetime, so comparisons are whole-day based."""
    if isinstance(value, datetime):
        return value.date()
    return value


def _friendly_duration(days: int) -> str:
    """Express a number of days as weeks when it divides evenly, otherwise days."""
    if days % 7 == 0:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''}"
    return f"{days} day{'s' if days != 1 else ''}"


def is_valid_posting_date(submission_date, posting_date, request_type=None) -> tuple[bool, str]:
    """
    Check whether a request was submitted with enough lead time before its target date.

    The required lead time depends on the request type (see LEAD_DAYS_BY_TYPE):
    post/reel = 2 weeks, misc = 3 weeks, website/photography = 3 days.

    Returns:
        (is_valid, reason)
    """
    key = _type_key(request_type)
    required = LEAD_DAYS_BY_TYPE.get(key, DEFAULT_LEAD_DAYS)
    date_noun = DATE_NOUN_BY_TYPE.get(key, "target date")

    lead_days = (_as_date(posting_date) - _as_date(submission_date)).days

    if lead_days < required:
        return False, (
            f"This request was submitted only **{lead_days} day(s)** before the {date_noun}. "
            f"These requests should be made at least **{_friendly_duration(required)}** in advance."
        )

    return True, (
        f"The {date_noun} is **{lead_days} day(s)** away — enough lead time."
    )


def get_posting_warning_embed(is_valid: bool, reason: str):
    """Create a Discord embed for the lead-time check."""
    import discord

    if is_valid:
        return discord.Embed(
            title="✅ Date OK",
            description=reason,
            color=0x57F287,  # Green
        )

    embed = discord.Embed(
        title="⚠️ Short Notice Warning",
        description=reason,
        color=0xFEE75C,  # Yellow
    )
    embed.add_field(
        name="⏰ Impact",
        value="Requests made on short notice may not be completed in time.",
        inline=False,
    )
    embed.set_footer(text="Please submit requests with enough lead time.")
    return embed
