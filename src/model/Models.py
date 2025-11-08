from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RequestStatus(str, Enum):
    IN_QUEUE = "in_queue"
    IN_PROGRESS = "in_progress"
    AWAITING_POSTING = "awaiting_posting"
    DONE = "done"
    BLOCKED = "blocked"

class RequestType(str, Enum):
    REEL = "reel"
    POST = "post"

@dataclass
class Request:
    """
    Python representation of the Request JPA entity.
    Maps to the 'requests' table in the database.
    """
    
    # DISCORD RELATED FIELDS
    # This includes stuff like channel IDs, message IDs, guild IDs, etc.
    channel_id: int | None = None
    requester_id: int | None = None
    requester_department_id: int | None = None
    assigned_to_id: int | None = None
    additional_assignee_id: int | None = None
    main_message_id: int | None = None
    
    # MARKETING REQUEST RELATED FIELDS
    # Everything else related to the request, but not directly related to Discord
    title: str = ""  # Max length 255 in DB
    description: str = "" # Max length 4000 in DB
    status: RequestStatus = RequestStatus.IN_QUEUE
    type: RequestType = RequestType.POST
    posting_date: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    room: str | None = None
    signup_url: str | None = None