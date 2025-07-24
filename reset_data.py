#!/usr/bin/env python3
"""
Drink Reminder Data Reset Utility

This script allows you to reset the app's session data from the command line.
Useful when you notice incorrect hydration levels or accumulated errors.
"""

import sys
import argparse
from pathlib import Path
from persistent_storage import storage

def main():
    parser = argparse.ArgumentParser(description='Reset Drink Reminder app data')
    parser.add_argument('--complete', action='store_true', 
                       help='Reset all data including lifetime statistics (default: preserve lifetime stats)')
    parser.add_argument('--confirm', action='store_true',
                       help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    # Check if data directory exists
    data_dir = Path("data")
    if not data_dir.exists():
        print("❌ Data directory not found. No data to reset.")
        return
    
    # Show current stats before reset
    try:
        app_state = storage.load_app_state()
        print("📊 Current Data:")
        print(f"   Daily consumption: {app_state.get('daily_consumed_ml', 0):.0f}ml")
        print(f"   Event counts: {len(app_state.get('event_counts', {}))}")
        
        if 'lifetime_stats' in app_state:
            stats = app_state['lifetime_stats']
            print(f"   Lifetime stats: {stats['total_sessions']} sessions, {stats['total_ml_consumed']:.0f}ml total")
    except Exception as e:
        print(f"⚠️ Error reading current data: {e}")
    
    # Confirm reset
    if not args.confirm:
        reset_type = "complete" if args.complete else "session (preserving lifetime stats)"
        confirm = input(f"\n🔄 Reset {reset_type}? (y/N): ").lower().strip()
        if confirm != 'y':
            print("Reset cancelled.")
            return
    
    # Perform reset
    try:
        preserve_lifetime = not args.complete
        success = storage.reset_session_data(preserve_lifetime_stats=preserve_lifetime)
        
        if success:
            if args.complete:
                print("✅ Complete data reset successful!")
            else:
                print("✅ Session reset successful! Lifetime statistics preserved.")
            print("\n💡 You can now restart the app with clean data.")
        else:
            print("❌ Reset failed.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error during reset: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 