import os
from typing import List, Optional
from datetime import datetime

import aiohttp
from aiohttp import BasicAuth

from src.model.Models import Request, RequestStatus, RequestType


class DatabaseClient:
    """Async client for interacting with the Command Centre database API."""
    
    def __init__(self, bot_auth: bool = True):
        """
        Initialize the database client.
        
        Args:
            bot_auth: If True, authenticate as discord-bot. If False, use API key auth.
        """
        self.base_url = os.getenv("DATABASE_API_URL")
        self.api_key = os.getenv("DATABASE_API_KEY")
        
        if not self.base_url:
            raise ValueError("DATABASE_API_URL environment variable is required")
        
        self.bot_auth = bot_auth
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Connection pool settings for better performance
        self._connector_limit = 10  # Max concurrent connections
        self._connector_limit_per_host = 5
    
    async def __aenter__(self):
        """Context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists with connection pooling."""
        if self._session is None or self._session.closed:
            headers = {}
            auth = None
            
            if self.bot_auth:
                # Authenticate as discord-bot for backend operations
                auth = BasicAuth("discord-bot", self.api_key or "")
            elif self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # Create connector with connection pooling for better performance
            connector = aiohttp.TCPConnector(
                limit=self._connector_limit,
                limit_per_host=self._connector_limit_per_host,
                ttl_dns_cache=300,  # Cache DNS for 5 minutes
                keepalive_timeout=30  # Keep connections alive for reuse
            )
            
            self._session = aiohttp.ClientSession(
                headers=headers,
                auth=auth,
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30)  # 30 second timeout
            )
    
    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _parse_datetime(self, datetime_str: str) -> datetime:
        """
        Parse datetime string, handling high-precision fractional seconds.
        
        Python's fromisoformat only supports up to 6 digits for microseconds,
        but .NET can send 7 digits. This truncates to 6 digits.
        Also pads short fractional seconds to 6 digits.
        """
        # If there's a fractional seconds part, normalize it to 6 digits
        if '.' in datetime_str:
            # Split on the decimal point
            parts = datetime_str.split('.')
            if len(parts) == 2:
                # Get the integer part and fractional part
                integer_part = parts[0]
                fractional_part = parts[1]
                
                # Extract only digits for fractional seconds
                # Keep any timezone info after the fractional seconds
                microseconds = ""
                timezone = ""
                for i, char in enumerate(fractional_part):
                    if char.isdigit():
                        if len(microseconds) < 6:
                            microseconds += char
                    else:
                        # Hit timezone or other character
                        timezone = fractional_part[i:]
                        break
                else:
                    # All characters were digits, check if we need to truncate
                    if len(fractional_part) > 6:
                        microseconds = fractional_part[:6]
                    else:
                        microseconds = fractional_part
                
                # Pad microseconds to 6 digits if shorter
                if microseconds:
                    microseconds = microseconds.ljust(6, '0')
                    datetime_str = f"{integer_part}.{microseconds}{timezone}"
                else:
                    datetime_str = f"{integer_part}{timezone}"
        
        return datetime.fromisoformat(datetime_str)
    
    def _parse_request(self, data: dict) -> Request:
        """Convert API response dict to Request dataclass."""
        # Convert camelCase to snake_case for Python
        parsed_data = {
            "channel_id": data.get("channelID"),
            "requester_id": data.get("requesterID"),
            "requester_department_id": data.get("requesterDepartmentID"),
            "assigned_to_id": data.get("assignedToID"),
            "additional_assignee_id": data.get("additionalAsigneeID"),
            "main_message_id": data.get("mainMessageID"),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "room": data.get("room"),
            "signup_url": data.get("signupUrl"),
        }
        
        # Convert datetime strings to datetime objects
        if data.get("postingDate"):
            parsed_data["posting_date"] = self._parse_datetime(data["postingDate"])
        if data.get("createdAt"):
            parsed_data["created_at"] = self._parse_datetime(data["createdAt"])
        if data.get("updatedAt"):
            parsed_data["updated_at"] = self._parse_datetime(data["updatedAt"])
        
        # Convert status string to enum
        if data.get("status"):
            parsed_data["status"] = RequestStatus(data["status"].lower())
        
        # Convert request type string to enum
        if data.get("requestType"):
            parsed_data["type"] = RequestType(data["requestType"].lower())
        
        return Request(**parsed_data)
    
    def _request_to_dict(self, request: Request) -> dict:
        """Convert Request dataclass to API-compatible dict (camelCase)."""
        return {
            "channelID": request.channel_id,
            "requesterID": request.requester_id,
            "requesterDepartmentID": request.requester_department_id,
            "assignedToID": request.assigned_to_id,
            "additionalAsigneeID": request.additional_assignee_id,
            "title": request.title,
            "description": request.description,
            "mainMessageID": request.main_message_id,
            "status": request.status.value.upper() if request.status else None,
            "postingDate": request.posting_date.isoformat() if request.posting_date else None,
            "room": request.room,
            "signupUrl": request.signup_url,
            "requestType": request.type.value.upper()
        }
    
    async def get_request_by_channel_id(self, channel_id: int) -> Optional[Request]:
        """
        Fetch a single request by channel ID.
        
        Endpoint: GET /api/requests/channel/{channelId}
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/requests/channel/{channel_id}") as response:
                response.raise_for_status()
                data = await response.json()
                return self._parse_request(data)
        except aiohttp.ClientError as e:
            print(f"Error fetching request {channel_id}: {e}")
            return None
    
    async def get_all_requests(self) -> List[Request]:
        """
        Fetch all requests.
        
        Endpoint: GET /api/requests
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/requests") as response:
                response.raise_for_status()
                data = await response.json()
                return [self._parse_request(req) for req in data]
        except aiohttp.ClientError as e:
            print(f"Error fetching requests: {e}")
            return []
    
    async def get_requests_by_status(self, status: RequestStatus) -> List[Request]:
        """
        Fetch requests filtered by status.
        
        Endpoint: GET /api/requests/status/{status}
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/requests/status/{status.value.upper()}") as response:
                response.raise_for_status()
                data = await response.json()
                return [self._parse_request(req) for req in data]
        except aiohttp.ClientError as e:
            print(f"Error fetching requests by status: {e}")
            return []
    
    async def get_requests_by_requester(self, requester_id: int) -> List[Request]:
        """
        Fetch requests by the user who created them.
        
        Endpoint: GET /api/requests/requester/{requesterId}
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/requests/requester/{requester_id}") as response:
                response.raise_for_status()
                data = await response.json()
                return [self._parse_request(req) for req in data]
        except aiohttp.ClientError as e:
            print(f"Error fetching requests by requester: {e}")
            return []
    
    async def get_requests_by_assigned_to(self, assigned_to_id: int) -> List[Request]:
        """
        Fetch requests assigned to a specific user.
        
        Endpoint: GET /api/requests/assigned/{assignedToId}
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/requests/assigned/{assigned_to_id}") as response:
                response.raise_for_status()
                data = await response.json()
                return [self._parse_request(req) for req in data]
        except aiohttp.ClientError as e:
            print(f"Error fetching requests by assignee: {e}")
            return []
    
    async def create_request(self, request: Request) -> Optional[Request]:
        """
        Create a new request.
        
        Endpoint: POST /api/requests
        """
        await self._ensure_session()
        try:
            data = self._request_to_dict(request)
            async with self._session.post(f"{self.base_url}/api/requests", json=data) as response:
                response.raise_for_status()
                data = await response.json()
                return self._parse_request(data)
        except aiohttp.ClientError as e:
            print(f"Error creating request: {e}")
            return None
    
    async def update_request(self, channel_id: int, request: Request) -> Optional[Request]:
        """
        Update an existing request.
        
        Endpoint: PUT /api/requests/channel/{channelId}
        """
        await self._ensure_session()
        try:
            data = self._request_to_dict(request)
            async with self._session.put(
                f"{self.base_url}/api/requests/channel/{channel_id}",
                json=data
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return self._parse_request(data)
        except aiohttp.ClientError as e:
            print(f"Error updating request: {e}")
            return None
    
    async def delete_request(self, channel_id: int) -> bool:
        """
        Delete a request by channel ID.
        
        Endpoint: DELETE /api/requests/channel/{channelId}
        """
        await self._ensure_session()
        try:
            async with self._session.delete(f"{self.base_url}/api/requests/channel/{channel_id}") as response:
                response.raise_for_status()
                return True
        except aiohttp.ClientError as e:
            print(f"Error deleting request {channel_id}: {e}")
            return False
    
    async def assign_request(self, channel_id: int, assigned_to_id: int) -> Optional[Request]:
        """
        Assign a request to a user.
        
        Endpoint: PATCH /api/requests/channel/{channelId}/assign/{assignedToId}
        """
        await self._ensure_session()
        try:
            async with self._session.patch(
                f"{self.base_url}/api/requests/channel/{channel_id}/assign/{assigned_to_id}"
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return self._parse_request(data)
        except aiohttp.ClientError as e:
            print(f"Error assigning request {channel_id}: {e}")
            return None
    
    async def set_request_status(self, channel_id: int, status: RequestStatus) -> Optional[Request]:
        """
        Set the status of a request.
        
        Endpoint: PATCH /api/requests/channel/{channelId}/status/{status}
        """
        await self._ensure_session()
        try:
            async with self._session.patch(
                f"{self.base_url}/api/requests/channel/{channel_id}/status/{status.value}"
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return self._parse_request(data)
        except aiohttp.ClientError as e:
            print(f"Error setting request status {channel_id}: {e}")
            return None
    
    async def advance_request_to_next_status(self, channel_id: int) -> Optional[Request]:
        """
        Advance a request to the next status in the workflow.
        
        Endpoint: PATCH /api/requests/channel/{channelId}/advance
        """
        await self._ensure_session()
        try:
            async with self._session.patch(
                f"{self.base_url}/api/requests/channel/{channel_id}/advance"
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return self._parse_request(data)
        except aiohttp.ClientError as e:
            print(f"Error advancing request {channel_id}: {e}")
            return None
    
    async def update_requester_department(self, channel_id: int, department_id: int) -> Optional[Request]:
        """
        Update the requester's department for a request.
        
        Endpoint: PATCH /api/requests/channel/{channelId}/department/{departmentId}
        """
        await self._ensure_session()
        try:
            async with self._session.patch(
                f"{self.base_url}/api/requests/channel/{channel_id}/department/{department_id}"
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return self._parse_request(data)
        except aiohttp.ClientError as e:
            print(f"Error updating requester department {channel_id}: {e}")
            return None
    
    async def change_requester(self, channel_id: int, requester_id: int) -> Optional[Request]:
        """
        Change the requester of a request.
        
        Endpoint: PATCH /api/requests/channel/{channelId}/requester/{requesterId}
        """
        await self._ensure_session()
        try:
            async with self._session.patch(
                f"{self.base_url}/api/requests/channel/{channel_id}/requester/{requester_id}"
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return self._parse_request(data)
        except aiohttp.ClientError as e:
            print(f"Error changing requester for request {channel_id}: {e}")
            return None
