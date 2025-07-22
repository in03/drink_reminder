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
                "event_counts": {}
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
    
    def save_app_state(self, app_start_time: datetime, event_counts: Dict[str, int]):
        """Save application state"""
        data = {
            "app_start_time": app_start_time.isoformat(),
            "last_shutdown_time": datetime.now().isoformat(),
            "event_counts": event_counts
        }
        self._write_json(self.app_state_file, data)
    
    def load_app_state(self) -> Dict[str, Any]:
        """Load application state"""
        return self._read_json(self.app_state_file, {
            "app_start_time": None,
            "last_shutdown_time": None,
            "event_counts": {}
        })
    
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