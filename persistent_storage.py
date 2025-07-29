import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import asyncio
from pathlib import Path

@dataclass
class TimerState:
    name: str
    last_triggered: Optional[str]  # ISO format datetime
    interval_minutes: int
    random_variance_minutes: int
    is_active: bool
    next_trigger_time: Optional[str]  # ISO format datetime

@dataclass 
class EventLogEntry:
    timestamp: str  # ISO format datetime
    event_type: str
    severity: int
    data: Dict[str, Any]
    source: str = "app"
    timer_name: Optional[str] = None  # For timer-specific events

class PersistentStorage:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        self.timer_state_file = self.data_dir / "timer_states.json"
        self.event_log_file = self.data_dir / "event_log.json"
        self.app_state_file = self.data_dir / "app_state.json"
        
        # Ensure files exist
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        """Create empty files if they don't exist"""
        if not self.timer_state_file.exists():
            self._write_json(self.timer_state_file, {})
        
        if not self.event_log_file.exists():
            self._write_json(self.event_log_file, {"events": []})
        
        if not self.app_state_file.exists():
            self._write_json(self.app_state_file, {
                "app_start_time": None,
                "last_shutdown_time": None,
                "event_counts": {},
                "bottle_weight": None,  # Will be set to default if not saved
                "daily_consumed_ml": 0.0,
                "last_daily_reset": None,
                "config_overrides": {},  # Configuration overrides from UI
                "lifetime_stats": {
                    "total_sessions": 0,
                    "total_ml_consumed": 0.0,
                    "total_drink_events": 0,
                    "days_tracked": 0
                }
            })
    
    def _read_json(self, file_path: Path, default=None):
        """Safely read JSON file"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading {file_path}: {e}")
            return default or {}
    
    def _write_json(self, file_path: Path, data):
        """Safely write JSON file"""
        try:
            # Write to temp file first, then rename for atomic operation
            temp_file = file_path.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            temp_file.rename(file_path)
        except Exception as e:
            print(f"Error writing {file_path}: {e}")
    
    def save_timer_states(self, timer_states: Dict[str, TimerState]):
        """Save timer states to file"""
        data = {name: asdict(state) for name, state in timer_states.items()}
        self._write_json(self.timer_state_file, data)
    
    def load_timer_states(self) -> Dict[str, TimerState]:
        """Load timer states from file"""
        data = self._read_json(self.timer_state_file, {})
        states = {}
        for name, state_dict in data.items():
            try:
                states[name] = TimerState(**state_dict)
            except Exception as e:
                print(f"Error loading timer state {name}: {e}")
        return states
    
    def log_event(self, event: EventLogEntry):
        """Append event to log file"""
        try:
            data = self._read_json(self.event_log_file, {"events": []})
            data["events"].append(asdict(event))
            
            # Keep only last 1000 events to prevent file from growing too large
            if len(data["events"]) > 1000:
                data["events"] = data["events"][-1000:]
            
            self._write_json(self.event_log_file, data)
        except Exception as e:
            print(f"Error logging event: {e}")
    
    def get_recent_events(self, hours: int = 24) -> List[EventLogEntry]:
        """Get events from the last N hours"""
        try:
            data = self._read_json(self.event_log_file, {"events": []})
            cutoff_time = datetime.now().replace(second=0, microsecond=0)
            cutoff_time = cutoff_time - timedelta(hours=hours)
            
            recent_events = []
            for event_dict in data["events"]:
                try:
                    event = EventLogEntry(**event_dict)
                    event_time = datetime.fromisoformat(event.timestamp)
                    if event_time >= cutoff_time:
                        recent_events.append(event)
                except Exception:
                    continue
            
            return recent_events
        except Exception as e:
            print(f"Error getting recent events: {e}")
            return []
    
    def save_app_state(self, app_start_time: datetime, event_counts: Dict[str, int], bottle_weight: int = None, daily_consumed_ml: float = None, last_daily_reset: str = None, config_overrides: Dict[str, Any] = None):
        """Save application state including bottle weight, daily consumption, and configuration overrides"""
        # Load existing data to preserve other fields
        existing_data = self.load_app_state()
        
        data = {
            "app_start_time": app_start_time.isoformat(),
            "last_shutdown_time": datetime.now().isoformat(),
            "event_counts": event_counts
        }
        
        # Only update bottle_weight if provided
        if bottle_weight is not None:
            data["bottle_weight"] = bottle_weight
        elif "bottle_weight" in existing_data:
            data["bottle_weight"] = existing_data["bottle_weight"]
            
        # Only update daily consumption if provided
        if daily_consumed_ml is not None:
            data["daily_consumed_ml"] = daily_consumed_ml
        elif "daily_consumed_ml" in existing_data:
            data["daily_consumed_ml"] = existing_data["daily_consumed_ml"]
            
        # Only update last daily reset if provided
        if last_daily_reset is not None:
            data["last_daily_reset"] = last_daily_reset
        elif "last_daily_reset" in existing_data:
            data["last_daily_reset"] = existing_data["last_daily_reset"]
            
        # Handle configuration overrides
        if config_overrides is not None:
            data["config_overrides"] = config_overrides
        elif "config_overrides" in existing_data:
            data["config_overrides"] = existing_data["config_overrides"]
        else:
            data["config_overrides"] = {}
            
        # Initialize lifetime stats if not present
        if "lifetime_stats" not in existing_data:
            data["lifetime_stats"] = {
                "total_sessions": 0,
                "total_ml_consumed": 0.0,
                "total_drink_events": 0,
                "days_tracked": 0
            }
        else:
            data["lifetime_stats"] = existing_data["lifetime_stats"]
            
        self._write_json(self.app_state_file, data)
    
    def save_daily_consumption(self, daily_consumed_ml: float, last_daily_reset: str):
        """Save just the daily consumption data to app state"""
        existing_data = self.load_app_state()
        existing_data["daily_consumed_ml"] = daily_consumed_ml
        existing_data["last_daily_reset"] = last_daily_reset
        self._write_json(self.app_state_file, existing_data)
    
    def save_bottle_weight(self, bottle_weight: int):
        """Save just the bottle weight to app state"""
        existing_data = self.load_app_state()
        existing_data["bottle_weight"] = bottle_weight
        self._write_json(self.app_state_file, existing_data)
    
    def update_lifetime_stats(self, ml_consumed: float = 0, drink_events: int = 0, new_session: bool = False, new_day: bool = False):
        """Update lifetime statistics"""
        existing_data = self.load_app_state()
        
        if "lifetime_stats" not in existing_data:
            existing_data["lifetime_stats"] = {
                "total_sessions": 0,
                "total_ml_consumed": 0.0,
                "total_drink_events": 0,
                "days_tracked": 0
            }
        
        stats = existing_data["lifetime_stats"]
        
        if new_session:
            stats["total_sessions"] += 1
        if new_day:
            stats["days_tracked"] += 1
        if ml_consumed > 0:
            stats["total_ml_consumed"] += ml_consumed
        if drink_events > 0:
            stats["total_drink_events"] += drink_events
            
        existing_data["lifetime_stats"] = stats
        self._write_json(self.app_state_file, existing_data)
    
    def load_app_state(self) -> Dict[str, Any]:
        """Load application state"""
        return self._read_json(self.app_state_file, {
            "app_start_time": None,
            "last_shutdown_time": None,
            "event_counts": {},
            "bottle_weight": None,
            "daily_consumed_ml": 0.0,
            "last_daily_reset": None,
            "config_overrides": {},  # Configuration overrides from UI
            "lifetime_stats": {
                "total_sessions": 0,
                "total_ml_consumed": 0.0,
                "total_drink_events": 0,
                "days_tracked": 0
            }
        })
    
    def reset_session_data(self, preserve_lifetime_stats: bool = True):
        """Reset current session data while optionally preserving lifetime statistics
        
        Args:
            preserve_lifetime_stats: If True, keep lifetime stats. If False, reset everything.
        """
        try:
            existing_data = self.load_app_state()
            
            # Update lifetime stats with current session before reset
            if preserve_lifetime_stats and "lifetime_stats" in existing_data:
                lifetime_stats = existing_data["lifetime_stats"]
                # If there was daily consumption, add it to lifetime totals
                if existing_data.get("daily_consumed_ml", 0) > 0:
                    lifetime_stats["total_ml_consumed"] += existing_data["daily_consumed_ml"]
                    lifetime_stats["total_drink_events"] += existing_data.get("event_counts", {}).get("drink", 0)
            else:
                lifetime_stats = {
                    "total_sessions": 0,
                    "total_ml_consumed": 0.0,
                    "total_drink_events": 0,
                    "days_tracked": 0
                }
            
            # Reset session data
            reset_data = {
                "app_start_time": None,
                "last_shutdown_time": datetime.now().isoformat(),
                "event_counts": {},  # Reset all event counts
                "bottle_weight": existing_data.get("bottle_weight", None),  # Preserve bottle weight
                "daily_consumed_ml": 0.0,  # Reset daily consumption
                "last_daily_reset": datetime.now().date().isoformat(),  # Reset to today
                "lifetime_stats": lifetime_stats if preserve_lifetime_stats else {
                    "total_sessions": 0,
                    "total_ml_consumed": 0.0,
                    "total_drink_events": 0,
                    "days_tracked": 0
                }
            }
            
            self._write_json(self.app_state_file, reset_data)
            
            # Also reset timer states
            self._write_json(self.timer_state_file, {})
            
            # Clear event log but keep a few recent entries for reference
            if preserve_lifetime_stats:
                # Keep last 5 events for context
                event_data = self._read_json(self.event_log_file, {"events": []})
                if len(event_data["events"]) > 5:
                    event_data["events"] = event_data["events"][-5:]
                self._write_json(self.event_log_file, event_data)
            else:
                # Complete reset
                self._write_json(self.event_log_file, {"events": []})
            
            print(f"✅ Session data reset complete. Lifetime stats {'preserved' if preserve_lifetime_stats else 'also reset'}.")
            return True
            
        except Exception as e:
            print(f"❌ Error resetting session data: {e}")
            return False
    
    def cleanup_old_logs(self, days: int = 30):
        """Remove log entries older than specified days"""
        try:
            data = self._read_json(self.event_log_file, {"events": []})
            cutoff_time = datetime.now().replace(second=0, microsecond=0)
            cutoff_time = cutoff_time - timedelta(days=days)
            
            filtered_events = []
            for event_dict in data["events"]:
                try:
                    event_time = datetime.fromisoformat(event_dict["timestamp"])
                    if event_time >= cutoff_time:
                        filtered_events.append(event_dict)
                except Exception:
                    continue
            
            data["events"] = filtered_events
            self._write_json(self.event_log_file, data)
            print(f"Cleaned up logs older than {days} days")
        except Exception as e:
            print(f"Error cleaning up logs: {e}")

# Global storage instance
storage = PersistentStorage() 