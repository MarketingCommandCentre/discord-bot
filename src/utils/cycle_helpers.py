"""
Utilities for handling marketing cycle logic.

Marketing operates on a 2-week cycle system:
- Submit requests before a production cycle starts
- Production happens during the 2-week production cycle
- Posting happens during the subsequent 2-week posting cycle
"""

from datetime import datetime, timedelta

# Define the reference cycle start date (first day of a production cycle)
# This should be a Monday when a production cycle started
CYCLE_START_DATE = datetime(2025, 11, 2)  # Adjust this to your actual cycle start

# Cycle length in days
CYCLE_LENGTH_DAYS = 14


def get_current_cycle_info(reference_date: datetime = None) -> dict:
    """
    Get information about the current cycle.
    
    Args:
        reference_date: The date to check. Defaults to now.
        
    Returns:
        dict with:
            - cycle_number: Which cycle we're in (0-based from CYCLE_START_DATE)
            - cycle_start: Start date of current cycle
            - cycle_end: End date of current cycle
            - days_into_cycle: How many days into the current cycle
            - is_production_cycle: Whether this is a production cycle (even cycles: 0, 2, 4...)
            - is_posting_cycle: Whether this is a posting cycle (odd cycles: 1, 3, 5...)
    """
    if reference_date is None:
        reference_date = datetime.now()
    
    # Calculate how many days since the reference cycle start
    days_since_start = (reference_date - CYCLE_START_DATE).days
    
    # Calculate which cycle we're in (0-based)
    cycle_number = days_since_start // CYCLE_LENGTH_DAYS
    
    # Calculate the start and end of the current cycle
    cycle_start = CYCLE_START_DATE + timedelta(days=cycle_number * CYCLE_LENGTH_DAYS)
    cycle_end = cycle_start + timedelta(days=CYCLE_LENGTH_DAYS - 1, hours=23, minutes=59, seconds=59)
    
    # Calculate days into current cycle
    days_into_cycle = (reference_date - cycle_start).days
    
    # Even cycles (0, 2, 4...) are production, odd cycles (1, 3, 5...) are posting
    is_production_cycle = cycle_number % 2 == 0
    is_posting_cycle = cycle_number % 2 == 1
    
    return {
        "cycle_number": cycle_number,
        "cycle_start": cycle_start,
        "cycle_end": cycle_end,
        "days_into_cycle": days_into_cycle,
        "is_production_cycle": is_production_cycle,
        "is_posting_cycle": is_posting_cycle
    }


def get_posting_cycle_for_request(submission_date: datetime) -> dict:
    """
    Given a request submission date, determine when it can be posted.
    
    Rules:
    - Request must be submitted BEFORE a production cycle starts
    - It will be produced during that production cycle (2 weeks)
    - It can be posted during the following posting cycle (next 2 weeks)
    
    Args:
        submission_date: When the request was submitted
        
    Returns:
        dict with:
            - production_cycle_start: When production will happen
            - production_cycle_end: When production ends
            - posting_cycle_start: When posting can happen
            - posting_cycle_end: When posting window ends
            - submission_cycle_number: Which cycle the submission falls in
    """
    submission_info = get_current_cycle_info(submission_date)
    
    # Determine which production cycle this request will be produced in
    # Rule: Request goes to the NEXT production cycle after submission
    if submission_info["is_production_cycle"]:
        # Submitted during a production cycle - too late for this one, goes to immediate next production cycle
        # Current production cycle -> next posting cycle -> next production cycle (+ 2 cycles)
        # But we want the IMMEDIATE next production, which is +2
        production_cycle_number = submission_info["cycle_number"] + 1
    else:
        # Submitted during a posting cycle - goes to next production cycle (immediate next)
        # Current posting cycle -> next production cycle (+ 1 cycle)
        production_cycle_number = submission_info["cycle_number"] + 1
    
    # Calculate production cycle dates
    production_start = CYCLE_START_DATE + timedelta(days=production_cycle_number * CYCLE_LENGTH_DAYS)
    production_end = production_start + timedelta(days=CYCLE_LENGTH_DAYS - 1, hours=23, minutes=59, seconds=59)
    
    # Posting happens in the cycle after production
    posting_start = production_end + timedelta(seconds=1)
    posting_end = posting_start + timedelta(days=CYCLE_LENGTH_DAYS - 1)
    
    return {
        "production_cycle_start": production_start,
        "production_cycle_end": production_end,
        "posting_cycle_start": posting_start,
        "posting_cycle_end": posting_end,
        "submission_cycle_number": submission_info["cycle_number"]
    }


def is_valid_posting_date(submission_date: datetime, posting_date: datetime) -> tuple[bool, str]:
    """
    Check if a posting date is valid for a request submitted on a given date.
    
    Args:
        submission_date: When the request was submitted
        posting_date: The proposed posting date
        
    Returns:
        tuple of (is_valid: bool, reason: str)
            - is_valid: True if the posting date meets criteria
            - reason: Explanation of why it's valid or invalid
    """
    posting_info = get_posting_cycle_for_request(submission_date)
    
    posting_cycle_start = posting_info["posting_cycle_start"]
    posting_cycle_end = posting_info["posting_cycle_end"]
    
    # Check if posting date falls within the valid posting window
    if posting_date < posting_cycle_start:
        days_early = (posting_cycle_start - posting_date).days
        return False, f"Posting date is {days_early} day(s) too early. Earliest valid posting date is {posting_cycle_start.strftime('%B %d, %Y')}."
    
    return True, f"Valid! Posting date falls within the posting window ({posting_cycle_start.strftime('%B %d')} to {posting_cycle_end.strftime('%B %d, %Y')})."


def get_friendly_cycle_message(submission_date: datetime) -> str:
    """
    Get a user-friendly message explaining when a request will be produced and posted.
    
    Args:
        submission_date: When the request was submitted
        
    Returns:
        A formatted string explaining the timeline
    """
    posting_info = get_posting_cycle_for_request(submission_date)
    
    production_start = posting_info["production_cycle_start"]
    production_end = posting_info["production_cycle_end"]
    posting_start = posting_info["posting_cycle_start"]
    posting_end = posting_info["posting_cycle_end"]
    
    return (
        f"**📅 Production Cycle:** {production_start.strftime('%b %d')} - {production_end.strftime('%b %d, %Y')}\n"
        f"**📤 Posting Window:** {posting_start.strftime('%b %d')} - {posting_end.strftime('%b %d, %Y')}"
    )


def get_cycle_warning_embed(submission_date: datetime, posting_date: datetime, is_valid: bool, reason: str):
    """
    Create a Discord embed for cycle validation warnings.
    
    Args:
        submission_date: When the request was submitted
        posting_date: The proposed posting date
        is_valid: Whether the posting date is valid
        reason: The validation reason/message
        
    Returns:
        Discord embed object (requires discord.py)
    """
    import discord
    
    if is_valid:
        embed = discord.Embed(
            title="✅ Posting Date Valid",
            description=reason,
            color=0x57F287  # Green
        )
    else:
        embed = discord.Embed(
            title="⚠️ Posting Date Warning",
            description=reason,
            color=0xFEE75C  # Yellow
        )
        
        # Add the expected timeline
        timeline = get_friendly_cycle_message(submission_date)
        embed.add_field(
            name="Expected Timeline",
            value=timeline,
            inline=False
        )
        
        embed.add_field(
            name="⏰ Impact",
            value="Your request may not be delivered on time if the posting date falls outside the valid window.",
            inline=False
        )
    
    embed.set_footer(text="Marketing operates on a 2-week production + 2-week posting cycle")
    return embed
