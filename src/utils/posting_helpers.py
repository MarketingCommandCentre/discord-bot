"""
Posting-date helpers.

Marketing requests should be submitted at least two weeks before the desired
posting date. This module provides a simple lead-time check and a warning embed
that is shown in the request channel when a request is made on short notice.
"""

from datetime import datetime

# Minimum number of days a request should be submitted before its posting date.
MINIMUM_LEAD_DAYS = 14


def _as_date(value):
    """Return a date from a date or datetime, so comparisons are whole-day based."""
    if isinstance(value, datetime):
        return value.date()
    return value


def is_valid_posting_date(submission_date, posting_date) -> tuple[bool, str]:
    """
    Check whether a request was submitted with enough lead time before its posting date.

    A request is considered valid when the posting date is at least
    MINIMUM_LEAD_DAYS (2 weeks) after the submission date.

    Returns:
        (is_valid, reason)
    """
    lead_days = (_as_date(posting_date) - _as_date(submission_date)).days

    if lead_days < MINIMUM_LEAD_DAYS:
        return False, (
            f"This request was submitted only **{lead_days} day(s)** before the posting date. "
            f"Marketing requests should be made at least **{MINIMUM_LEAD_DAYS} days (2 weeks)** in advance."
        )

    return True, (
        f"Posting date is **{lead_days} day(s)** away — at least 2 weeks of lead time."
    )


def get_posting_warning_embed(is_valid: bool, reason: str):
    """Create a Discord embed for the posting-date lead-time check."""
    import discord

    if is_valid:
        return discord.Embed(
            title="✅ Posting Date OK",
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
        value="Requests made on short notice may not be completed in time for the posting date.",
        inline=False,
    )
    embed.set_footer(text="Please submit marketing requests at least 2 weeks before the posting date.")
    return embed
