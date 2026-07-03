"""
Service for generating mock marketing request content using the Anthropic API
(Claude Haiku).

The generator only produces the *content* of a request — the same fields a user
would type into the request form (title, description, posting date, room, signup
URL, type). Persistence and all Discord side effects (channel, role, message) are
handled by RequestManager.create_request, exactly as if the form had been
submitted.

Copyright (C) 2026 Ibrahim Chehab

This file is part of the Marketing Command Centre Discord Bot.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from anthropic import AsyncAnthropic

from src.model.Models import Request, RequestStatus, RequestType

logger = logging.getLogger(__name__)


class MockRequestGenerator:
    """Generate realistic-but-fictional marketing requests via Claude Haiku."""

    # The user explicitly asked for Haiku; it is the cheapest/fastest tier and
    # more than capable of inventing plausible form content.
    MODEL = "claude-haiku-4-5"

    # JSON schema the model must fill. Kept simple to satisfy structured-output
    # constraints (no string/number length bounds, enums for the fixed sets).
    _SCHEMA = {
        "type": "object",
        "properties": {
            "requests": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "type": {"type": "string", "enum": ["post", "reel"]},
                        "room": {"type": "string"},
                        "signup_url": {"type": "string"},
                        "days_until_posting": {"type": "integer"},
                    },
                    "required": [
                        "title",
                        "description",
                        "type",
                        "room",
                        "signup_url",
                        "days_until_posting",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requests"],
        "additionalProperties": False,
    }

    def __init__(self, api_key: Optional[str] = None):
        # AsyncAnthropic falls back to the ANTHROPIC_API_KEY env var (loaded from
        # .env by main.py) when no key is passed explicitly.
        self.client = AsyncAnthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    async def generate_requests(
        self, count: int, theme: Optional[str] = None
    ) -> List[Request]:
        """
        Generate ``count`` mock requests as content-only Request objects.

        The returned requests carry no channel_id, requester_id, or assignee — the
        caller sets the requester and hands them to RequestManager.create_request,
        which performs the full end-to-end creation. Status defaults to IN_QUEUE.
        """
        count = max(1, min(count, 10))
        raw = await self._call_model(count, theme)
        return [self._to_request(item) for item in raw[:count]]

    async def _call_model(self, count: int, theme: Optional[str]) -> List[dict]:
        """Call Claude Haiku and return the parsed list of request dicts."""
        prompt = (
            f"Generate {count} realistic but entirely fictional marketing content "
            "requests for a university student-life marketing team's command centre. "
            "Each request is what a club or department would submit asking the "
            "marketing team to produce a social media post or reel for an event or "
            "initiative.\n\n"
            "For each request provide:\n"
            "- title: a short event/campaign name\n"
            "- description: 1-3 sentences describing what is needed and any key "
            "details (audience, vibe, deliverables)\n"
            "- type: either \"post\" (static graphic) or \"reel\" (short video)\n"
            "- room: a plausible campus location or \"Online\" / \"Instagram\"\n"
            "- signup_url: a plausible fictional registration URL (use example.com "
            "or forms.gle style links)\n"
            "- days_until_posting: an integer 3-45 for how many days from now the "
            "content should be posted\n\n"
            "Make the requests varied and believable for a training environment."
        )
        if theme:
            prompt += f"\n\nCentre all of the mock requests around this theme/context: {theme}."

        response = await self.client.messages.create(
            model=self.MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": self._SCHEMA}},
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        data = self._parse_json(text)
        return data.get("requests", [])

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse the model's JSON, tolerating stray markdown code fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Drop the opening fence (``` or ```json) and the closing fence.
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3]
        return json.loads(cleaned)

    @staticmethod
    def _to_request(item: dict) -> Request:
        """Convert one generated dict into a content-only Request object."""
        try:
            days = int(item.get("days_until_posting", 7))
        except (TypeError, ValueError):
            days = 7
        posting_date = datetime.now() + timedelta(days=max(1, days))

        try:
            request_type = RequestType(str(item.get("type", "post")).lower())
        except ValueError:
            request_type = RequestType.POST

        return Request(
            title=(item.get("title") or "Untitled Mock Request")[:255],
            description=(item.get("description") or "")[:4000],
            type=request_type,
            status=RequestStatus.IN_QUEUE,
            posting_date=posting_date,
            room=(item.get("room") or None),
            signup_url=(item.get("signup_url") or None),
        )
