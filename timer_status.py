#!/usr/bin/env python3
"""
Timer Status Utility - Check current timer states without stopping the app
"""

import json
from datetime import datetime
from pathlib import Path

def format_duration(dt: datetime) -> str:
    """Format duration until trigger time"""
    from datetime import timezone
    
    # Convert to UTC for comparison
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    diff = dt - now
    
    if diff.total_seconds() < 0:
        return "⚠️  OVERDUE"
    
    total_seconds = int(diff.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    days = hours // 24
    hours = hours % 24
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def main():
    data_dir = Path("data")
    
    if not data_dir.exists():
        print("❌ Data directory not found. Is the app running?")
        return
    
    # Load timer states
    timer_file = data_dir / "timer_states.json"
    if not timer_file.exists():
        print("❌ Timer states file not found.")
        return
    
    with open(timer_file) as f:
        timers = json.load(f)
    
    # Load app state
    app_file = data_dir / "app_state.json"
    app_state = {}
    if app_file.exists():
        with open(app_file) as f:
            app_state = json.load(f)
    
    print("🍺 DRINK REMINDER - TIMER STATUS")
    print("=" * 40)
    
    from datetime import timezone
    local_time = datetime.now()
    utc_time = datetime.now(timezone.utc)
    print(f"📅 Local Time: {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌍 UTC Time: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if app_state.get('app_start_time'):
        start_time = datetime.fromisoformat(app_state['app_start_time'])
        print(f"🚀 App Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    print("\n⏰ TIMER STATES:")
    print("-" * 40)
    
    for name, timer in timers.items():
        status = "🟢 ACTIVE" if timer['is_active'] else "🔴 INACTIVE"
        interval = timer['interval_minutes']
        
        if timer['next_trigger_time']:
            next_trigger = datetime.fromisoformat(timer['next_trigger_time'])
            time_until = format_duration(next_trigger)
            next_str = f"{next_trigger.strftime('%H:%M:%S')} UTC"
        else:
            time_until = "NOT SET"
            next_str = "NOT SET"
        
        print(f"📌 {name.upper()}")
        print(f"   Status: {status}")
        print(f"   Interval: {interval} minutes")
        print(f"   Next Trigger: {next_str}")
        print(f"   Time Until: {time_until}")
        print()
    
    # Show recent events
    event_file = data_dir / "event_log.json" 
    if event_file.exists():
        with open(event_file) as f:
            events_data = json.load(f)
        
        recent_events = events_data.get('events', [])[-5:]
        if recent_events:
            print("📋 RECENT EVENTS (Last 5):")
            print("-" * 40)
            for event in recent_events:
                timestamp = datetime.fromisoformat(event['timestamp'])
                print(f"🕐 {timestamp.strftime('%H:%M:%S')} - {event['event_type']} (severity: {event['severity']})")

if __name__ == "__main__":
    main() 