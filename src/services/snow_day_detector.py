from dataclasses import dataclass
from typing import List
import aiohttp
from bs4 import BeautifulSoup


@dataclass
class CampusStatus:
    name: str
    status: str
    
    @property
    def is_open(self) -> bool:
        return self.status.lower() == "open"
    
    @property
    def is_closed(self) -> bool:
        return self.status.lower() == "closed"


class CampusStatusService:
    URL = "https://www.utoronto.ca/campus-status"
    
    async def get_all_statuses(self) -> List[CampusStatus]:
        """Fetch status for all campuses"""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.URL) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                statuses = []
                for item in soup.find_all('div', class_='campus-status'):
                    name = item.find('h2').text.strip()
                    status = item.find('div', class_='status-output').text.strip()
                    statuses.append(CampusStatus(name=name, status=status))
                
                return statuses
    
    async def all_open(self) -> bool:
        """Check if all campuses are open"""
        statuses = await self.get_all_statuses()
        return all(campus.is_open for campus in statuses)
    
    async def all_closed(self) -> bool:
        """Check if all campuses are closed"""
        statuses = await self.get_all_statuses()
        return all(campus.is_closed for campus in statuses)
    
    async def any_open(self) -> bool:
        """Check if any campus is open"""
        statuses = await self.get_all_statuses()
        return any(campus.is_open for campus in statuses)
    
x = CampusStatusService()

import asyncio

async def main():
    statuses = await x.get_all_statuses()
    for campus in statuses:
        print(f"{campus.name}: {campus.status}")
    print("All Open:", await x.all_open())
    print("All Closed:", await x.all_closed())
    print("Any Open:", await x.any_open())

if __name__ == "__main__":
    asyncio.run(main())