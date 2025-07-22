import asyncio
import aiohttp
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
import os

class TimeService:
    def __init__(self):
        self.api_time_offset = 0  # Offset between API time and system time
        self.last_sync_time = None
        self.time_apis = [
            "http://worldclockapi.com/api/json/utc/now", 
            # "https://timeapi.io/api/Time/current/zone?timeZone=UTC"  # Commented out to reduce API calls
        ]
    
    async def sync_time(self) -> bool:
        """Synchronize with time API and calculate offset"""
        for api_url in self.time_apis:
            try:
                timeout = aiohttp.ClientTimeout(total=10, connect=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(api_url, headers={'User-Agent': 'DrinkReminder/1.0'}) as response:
                        if response.status == 200:
                            data = await response.json()
                            api_time = self._parse_api_response(api_url, data)
                            if api_time:
                                system_time = datetime.now(timezone.utc)
                                self.api_time_offset = (api_time - system_time).total_seconds()
                                self.last_sync_time = system_time
                                print(f"✅ Time synced with {api_url}. Offset: {self.api_time_offset:.2f}s")
                                return True
                        else:
                            print(f"❌ HTTP {response.status} from {api_url}")
            except asyncio.TimeoutError:
                print(f"⏱️ Timeout connecting to {api_url}")
            except Exception as e:
                print(f"❌ Failed to sync with {api_url}: {e}")
                continue
        
        print("⚠️  Warning: Could not sync with any time API, using system time")
        self.last_sync_time = datetime.now(timezone.utc)
        self.api_time_offset = 0
        return False
    
    def _parse_api_response(self, api_url: str, data: dict) -> Optional[datetime]:
        """Parse different API response formats"""
        try:
            if "worldtimeapi.org" in api_url:
                # Handle worldtimeapi.org format
                dt_str = data['utc_datetime'].replace('Z', '+00:00')
                return datetime.fromisoformat(dt_str)
            elif "timeapi.io" in api_url:
                # Handle timeapi.io format - ensure timezone awareness
                dt_str = data['dateTime']
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    # If naive, assume UTC
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            elif "worldclockapi.com" in api_url:
                # Handle worldclockapi format
                dt_str = data['currentDateTime']
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    # If naive, assume UTC  
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
        except Exception as e:
            print(f"Failed to parse response from {api_url}: {e}")
            print(f"Raw response data: {data}")
        return None
    
    def get_accurate_time(self) -> datetime:
        """Get the most accurate current time available"""
        system_time = datetime.now(timezone.utc)
        
        # If we have a recent sync, apply the offset
        if self.last_sync_time and self.api_time_offset:
            time_since_sync = (system_time - self.last_sync_time).total_seconds()
            # Only use offset if sync was recent (within 1 hour)
            if time_since_sync < 3600:
                return system_time.replace(microsecond=0) + timedelta(seconds=self.api_time_offset)
        
        return system_time.replace(microsecond=0)
    
    async def ensure_time_sync(self):
        """Ensure time is synced once at startup only"""
        if not self.last_sync_time:
            await self.sync_time()

# Global time service instance
time_service = TimeService() 