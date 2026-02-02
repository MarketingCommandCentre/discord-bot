"""
Async client for interacting with the workload management API endpoints.
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime

import aiohttp
from aiohttp import BasicAuth


class WorkloadClient:
    """Async client for workload and cycle management endpoints."""
    
    def __init__(self, bot_auth: bool = False):
        """
        Initialize the workload client.
        
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
        self._connector_limit = 10
        self._connector_limit_per_host = 5
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists with connection pooling."""
        if self._session is None or self._session.closed:
            headers = {}
            auth = None
            
            if self.bot_auth:
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
                timeout=aiohttp.ClientTimeout(total=30)
            )
    
    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_content_creator_workload(self) -> Optional[Dict[str, Any]]:
        """
        Get all POST type requests for the current development cycle's posting period.
        
        Endpoint: GET /api/workload/content-creators
        
        Returns:
            Dict with cycleInfo, requestType, role, totalRequests, and requests list
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/workload/content-creators") as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Error fetching content creator workload: {e}")
            return None
    
    async def get_graphic_designer_workload(self) -> Optional[Dict[str, Any]]:
        """
        Get all REEL type requests for the current development cycle's posting period.
        
        Endpoint: GET /api/workload/graphic-designers
        
        Returns:
            Dict with cycleInfo, requestType, role, totalRequests, and requests list
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/workload/graphic-designers") as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Error fetching graphic designer workload: {e}")
            return None
    
    async def get_social_media_manager_workload(self) -> Optional[Dict[str, Any]]:
        """
        Get all requests (POST and REEL) for the current posting cycle.
        
        Endpoint: GET /api/workload/social-media-managers
        
        Returns:
            Dict with cycleInfo, requestType, role, totalRequests, and requests list
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/workload/social-media-managers") as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Error fetching social media manager workload: {e}")
            return None
    
    async def get_cycle_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about current development and posting cycles.
        
        Endpoint: GET /api/workload/cycle-info
        
        Returns:
            Dict with currentDevelopmentCycle and currentPostingCycle
        """
        await self._ensure_session()
        try:
            async with self._session.get(f"{self.base_url}/api/workload/cycle-info") as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Error fetching cycle info: {e}")
            return None
