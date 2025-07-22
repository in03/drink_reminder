from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass
from time_service import time_service
from persistent_storage import storage, EventLogEntry

@dataclass
class Event:
    event_type: str
    timestamp: datetime
    severity: int
    data: dict = None
    timer_name: str = None  # For timer-specific events

class EventManager:
    def __init__(self):
        self.events: List[Event] = []
        
        # Load existing event counts from storage
        app_state = storage.load_app_state()
        self.event_counts: Dict[str, int] = app_state.get('event_counts', {})
        
        # Load recent events from storage
        self._load_recent_events()
    
    def trigger_event(self, event_type: str, data: dict = None, timer_name: str = None) -> Event:
        """Trigger an event and calculate its severity based on previous occurrences"""
        # Get accurate timestamp
        current_time = time_service.get_accurate_time()
        
        # Create count key - use timer-specific key for timer events, global for others
        if timer_name:
            count_key = f"{timer_name}:{event_type}"
        else:
            count_key = event_type
        
        # Increment count for this event type (global or per-timer)
        self.event_counts[count_key] = self.event_counts.get(count_key, 0) + 1
        severity = self.event_counts[count_key]
        
        # Create the event
        event = Event(
            event_type=event_type,
            timestamp=current_time,
            severity=severity,
            data=data or {},
            timer_name=timer_name
        )
        
        self.events.append(event)
        
        # Log to persistent storage
        log_entry = EventLogEntry(
            timestamp=current_time.isoformat(),
            event_type=event_type,
            severity=severity,
            data=data or {},
            source="app",
            timer_name=timer_name
        )
        storage.log_event(log_entry)
        
        # Save updated event counts
        self._save_event_counts()
        
        return event
    
    def get_events_by_type(self, event_type: str) -> List[Event]:
        """Get all events of a specific type"""
        return [event for event in self.events if event.event_type == event_type]
    
    def get_latest_event(self, event_type: str) -> Event:
        """Get the most recent event of a specific type"""
        events = self.get_events_by_type(event_type)
        return events[-1] if events else None
    
    def get_recent_events(self, minutes: int = 60) -> List[Event]:
        """Get events from the last N minutes"""
        cutoff = datetime.now().replace(second=0, microsecond=0)
        cutoff = cutoff - timedelta(minutes=minutes)
        
        return [event for event in self.events if event.timestamp >= cutoff]
    
    def clear_events(self):
        """Clear all events (useful for testing)"""
        self.events.clear()
        self.event_counts.clear()
        
        # Save cleared state
        self._save_event_counts()
    
    def _load_recent_events(self):
        """Load recent events from storage"""
        try:
            recent_log_entries = storage.get_recent_events(hours=24)
            for log_entry in recent_log_entries:
                try:
                    # Handle backward compatibility for events without timer_name
                    timer_name = getattr(log_entry, 'timer_name', None)
                    event = Event(
                        event_type=log_entry.event_type,
                        timestamp=datetime.fromisoformat(log_entry.timestamp),
                        severity=log_entry.severity,
                        data=log_entry.data,
                        timer_name=timer_name
                    )
                    self.events.append(event)
                except Exception as e:
                    print(f"Error loading event from log: {e}")
        except Exception as e:
            print(f"Error loading recent events: {e}")
    
    def _save_event_counts(self):
        """Save current event counts to storage"""
        try:
            current_time = time_service.get_accurate_time()
            storage.save_app_state(current_time, self.event_counts)
        except Exception as e:
            print(f"Error saving event counts: {e}")
    
    def cleanup_old_events(self, hours: int = 24):
        """Remove old events from memory (keeps only recent ones)"""
        if not self.events:
            return
        
        cutoff_time = time_service.get_accurate_time().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_time = cutoff_time - timedelta(hours=hours)
        
        # Keep only recent events in memory
        self.events = [event for event in self.events if event.timestamp >= cutoff_time] 