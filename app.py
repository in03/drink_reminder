import os
import math
import asyncio
import signal
import atexit
from datetime import datetime, timedelta
from dotenv import load_dotenv
from nicegui import ui, run, app
from event_manager import EventManager, Event
from timer_manager import TimerManager
from time_service import time_service
from persistent_storage import storage

# Load environment variables
load_dotenv()

# Configuration class to handle settings
class Configuration:
    def __init__(self):
        # Load from environment variables first, then check local storage for overrides
        self._load_from_env()
        self._load_from_storage()
    
    def _load_from_env(self):
        """Load configuration from environment variables"""
        self.reminder_timer_minutes = int(os.getenv('REMINDER_TIMER_MINUTES', 45))
        self.drink_reminder_base = int(os.getenv('DRINK_REMINDER_BASE', 45))
        self.drink_reminder_limit = int(os.getenv('DRINK_REMINDER_LIMIT', 10))
        self.bad_orientation_base = int(os.getenv('BAD_ORIENTATION_BASE', 10))
        self.bad_orientation_limit = int(os.getenv('BAD_ORIENTATION_LIMIT', 2))
        self.empty_reminder_base = int(os.getenv('EMPTY_REMINDER_BASE', 10))
        self.empty_reminder_limit = int(os.getenv('EMPTY_REMINDER_LIMIT', 2))
        self.random_threshold_minutes = int(os.getenv('RANDOM_THRESHOLD_MINUTES', 5))
        self.min_weight = int(os.getenv('MIN_WEIGHT', 710))
        self.max_weight = int(os.getenv('MAX_WEIGHT', 1810))
        self.empty_bottle_weight = int(os.getenv('EMPTY_BOTTLE_WEIGHT', 710))
        self.full_bottle_weight = int(os.getenv('FULL_BOTTLE_WEIGHT', 1810))
        self.empty_threshold = int(os.getenv('EMPTY_THRESHOLD', 50))
        self.very_empty_threshold = int(os.getenv('VERY_EMPTY_THRESHOLD', 10))
        self.fill_threshold_percent = int(os.getenv('FILL_THRESHOLD_PERCENT', 10))
        self.drink_correction_threshold = int(os.getenv('DRINK_CORRECTION_THRESHOLD', 10))
        self.bad_orientation_interval = int(os.getenv('BAD_ORIENTATION_INTERVAL', 10))
        self.empty_reminder_interval = int(os.getenv('EMPTY_REMINDER_INTERVAL', 10))
        self.recalibrate_reminder_days = int(os.getenv('RECALIBRATE_REMINDER_DAYS', 2))
        self.min_timer_gap_minutes = int(os.getenv('MIN_TIMER_GAP_MINUTES', 1))
        self.orientation_threshold = int(os.getenv('ORIENTATION_THRESHOLD', 10))
        self.daily_goal_ml = int(os.getenv('DAILY_GOAL_IN_ML', 2000))
        self.hydration_start_hour = int(os.getenv('HYDRATION_START_HOUR', 7))
        self.hydration_end_hour = int(os.getenv('HYDRATION_END_HOUR', 22))
        self.reasonable_ml_per_hour = int(os.getenv('REASONABLE_ML_PER_HOUR', 130))
        self.simulator_mode = os.getenv('SIMULATOR_MODE', 'true').lower() == 'true'
        self.praise_window_minutes = float(os.getenv('PRAISE_WINDOW_MINUTES', 1.0))
    
    def _load_from_storage(self):
        """Load configuration overrides from local storage"""
        try:
            app_state = storage.load_app_state()
            config_overrides = app_state.get('config_overrides', {})
            
            # Apply overrides if they exist
            for key, value in config_overrides.items():
                if hasattr(self, key):
                    # Convert to appropriate type based on current value
                    current_value = getattr(self, key)
                    if isinstance(current_value, bool):
                        setattr(self, key, bool(value))
                    elif isinstance(current_value, int):
                        setattr(self, key, int(value))
                    elif isinstance(current_value, float):
                        setattr(self, key, float(value))
                    else:
                        setattr(self, key, value)
                    
            print(f"🔧 Loaded {len(config_overrides)} configuration overrides from storage")
        except Exception as e:
            print(f"Warning: Could not load configuration overrides: {e}")
    
    def save_to_storage(self):
        """Save current configuration to local storage"""
        try:
            # Get all configuration values that differ from defaults
            config_overrides = {}
            
            # Create a fresh config instance to compare against
            default_config = Configuration.__new__(Configuration)
            default_config._load_from_env()
            
            # Compare current values with defaults and save differences
            for attr in dir(self):
                if not attr.startswith('_') and hasattr(default_config, attr):
                    current_value = getattr(self, attr)
                    default_value = getattr(default_config, attr)
                    if current_value != default_value:
                        config_overrides[attr] = current_value
            
            # Save to storage
            app_state = storage.load_app_state()
            app_state['config_overrides'] = config_overrides
            
            # Save with current time and event counts
            from time_service import time_service
            current_time = time_service.get_accurate_time()
            # We need access to event_manager, so this will be called from the app
            
            print(f"🔧 Saved {len(config_overrides)} configuration overrides to storage")
            return config_overrides
        except Exception as e:
            print(f"Error saving configuration to storage: {e}")
            return {}

class DrinkReminderApp:
    def __init__(self):
        # Initialize configuration
        self.config = Configuration()
        
        # Use configuration values instead of direct environment variables
        self.reminder_timer_minutes = self.config.reminder_timer_minutes
        self.drink_reminder_base = self.config.drink_reminder_base
        self.drink_reminder_limit = self.config.drink_reminder_limit
        self.bad_orientation_base = self.config.bad_orientation_base
        self.bad_orientation_limit = self.config.bad_orientation_limit
        self.empty_reminder_base = self.config.empty_reminder_base
        self.empty_reminder_limit = self.config.empty_reminder_limit
        self.random_threshold_minutes = self.config.random_threshold_minutes
        self.min_weight = self.config.min_weight
        self.max_weight = self.config.max_weight
        self.empty_threshold = self.config.empty_threshold
        self.very_empty_threshold = self.config.very_empty_threshold
        self.fill_threshold_percent = self.config.fill_threshold_percent
        self.drink_correction_threshold = self.config.drink_correction_threshold
        self.bad_orientation_interval = self.config.bad_orientation_interval
        self.empty_reminder_interval = self.config.empty_reminder_interval
        self.recalibrate_reminder_days = self.config.recalibrate_reminder_days
        self.min_timer_gap_minutes = self.config.min_timer_gap_minutes
        self.orientation_threshold = self.config.orientation_threshold
        self.daily_goal_ml = self.config.daily_goal_ml
        self.hydration_start_hour = self.config.hydration_start_hour
        self.hydration_end_hour = self.config.hydration_end_hour
        self.reasonable_ml_per_hour = self.config.reasonable_ml_per_hour
        self.praise_window_minutes = self.config.praise_window_minutes
        
        # Application state
        self.current_weight = self.max_weight  # Start with full bottle
        self.previous_weight = self.current_weight
        
        # Load bottle weight from storage, use config if not available
        self._load_bottle_weight()
        self.accelerometer = {'x': 0, 'y': 0, 'z': 1}  # Start vertical (gravity down)
        self.is_empty_state = False
        
        # New hydration tracking state - dehydration level as core ground truth
        self.dehydration_level = 1.0  # Start with mild dehydration (realistic morning state)
        
        # Load daily consumption and reset date from storage
        app_state = storage.load_app_state()
        self.daily_consumed_ml = app_state.get('daily_consumed_ml', 0.0)
        saved_reset_date = app_state.get('last_daily_reset')
        
        if saved_reset_date:
            try:
                # Handle both date strings (YYYY-MM-DD) and datetime strings
                if 'T' in saved_reset_date:
                    # Full datetime string
                    self.last_daily_reset = datetime.fromisoformat(saved_reset_date).date()
                else:
                    # Date string only
                    from datetime import date
                    self.last_daily_reset = date.fromisoformat(saved_reset_date)
            except Exception as e:
                print(f"⚠️ Error parsing saved reset date '{saved_reset_date}': {e}")
                from datetime import datetime
                self.last_daily_reset = datetime.now().date()
        else:
            from datetime import datetime
            self.last_daily_reset = datetime.now().date()
        
        print(f"💧 Loaded daily consumption: {self.daily_consumed_ml}ml (last reset: {self.last_daily_reset})")
        
        # Force daily reset check on startup to handle overnight resets
        from datetime import datetime
        current_date = datetime.now().date()
        if current_date != self.last_daily_reset:
            print(f"🌅 Startup daily reset needed: {self.last_daily_reset} -> {current_date}")
            self._check_daily_reset()
        
        self.reminder_window_start = None  # Track when current reminder window started
        self.cumulative_hif_window = []  # Track drinks within current reminder window for cumulative HIF
        
        # Legacy dehydration severity (kept for compatibility)
        self.dehydration_severity = 0  # Will be replaced by dehydration_level
        
        # Event and timer managers
        self.event_manager = EventManager()
        self.timer_manager = TimerManager(self.min_timer_gap_minutes)
        
        # Reactive UI data - these will automatically update the UI when changed
        self.ui_data = {
            'weight_display': '',
            'status_display': '',
            'event_log': '',
            'timer_status': [],
            'hydration_status_display': ''
        }
        
        # Praise system configuration
        self.praise_window_drinks = []  # Track drinks within praise window
        
        # Initialize time service and storage
        self.app_start_time = None
        self._data_refresh_task = None  # Store reference for cleanup
        
        # Setup timers (but don't start them yet)
        self._setup_timers()
        
        # Data refresh task will be started when UI is created
    
    def _load_bottle_weight(self):
        """Load bottle weight from storage, use config default if not available"""
        try:
            app_state = storage.load_app_state()
            saved_bottle_weight = app_state.get('bottle_weight')
            
            if saved_bottle_weight is not None:
                self.bottle_weight = saved_bottle_weight
                print(f"🔧 Loaded bottle weight from storage: {self.bottle_weight}g")
            else:
                self.bottle_weight = self.config.empty_bottle_weight
                print(f"🔧 Using config default bottle weight: {self.bottle_weight}g (no saved weight found)")
        except Exception as e:
            print(f"❌ Error loading bottle weight: {e}, using config default: {self.config.empty_bottle_weight}g")
            self.bottle_weight = self.config.empty_bottle_weight
    
    def save_config_to_storage(self):
        """Save current configuration to storage"""
        try:
            config_overrides = self.config.save_to_storage()
            
            # Also save the overrides with current app state
            current_time = time_service.get_accurate_time()
            
            # Ensure last_daily_reset is properly formatted
            reset_date_str = None
            if self.last_daily_reset is not None:
                if hasattr(self.last_daily_reset, 'isoformat') and callable(getattr(self.last_daily_reset, 'isoformat', None)):
                    reset_date_str = self.last_daily_reset.isoformat()
                else:
                    reset_date_str = str(self.last_daily_reset)
            else:
                from datetime import date
                reset_date_str = date.today().isoformat()
            
            storage.save_app_state(
                current_time, 
                self.event_manager.event_counts, 
                self.bottle_weight,
                self.daily_consumed_ml,
                reset_date_str,
                config_overrides
            )
            
            print(f"🔧 Configuration saved to storage")
            return True
        except Exception as e:
            print(f"❌ Error saving configuration: {e}")
            return False
    
    def update_config_from_ui(self, new_config):
        """Update configuration from UI inputs"""
        try:
            # Update configuration object
            for key, value in new_config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    # Also update the app instance for immediate effect
                    if hasattr(self, key):
                        setattr(self, key, value)
            
            # Update weight bounds if they changed
            if 'empty_bottle_weight' in new_config:
                self.min_weight = self.config.empty_bottle_weight
            if 'full_bottle_weight' in new_config:
                self.max_weight = self.config.full_bottle_weight
                
            # Update UI elements if they exist
            if hasattr(self, 'weight_slider'):
                self.weight_slider.min = self.min_weight
                self.weight_slider.max = self.max_weight
                self.weight_slider.update()
            
            # Save to storage
            self.save_config_to_storage()
            
            # Update timers if interval-related configs changed
            timer_related_configs = ['drink_reminder_base', 'drink_reminder_limit', 'bad_orientation_base', 
                                   'bad_orientation_limit', 'empty_reminder_base', 'empty_reminder_limit']
            if any(key in new_config for key in timer_related_configs):
                self._update_reminder_timer_interval()
                self._update_empty_reminder_timer_interval()
                self._update_bad_orientation_timer_interval()
            
            print(f"🔄 Configuration updated: {list(new_config.keys())}")
            return True
        except Exception as e:
            print(f"❌ Error updating configuration: {e}")
            return False

    def _start_data_refresh_task(self):
        """Start the periodic data refresh task for reactive UI updates"""
        # Don't start if already running
        if self._data_refresh_task and not self._data_refresh_task.done():
            return
            
        async def refresh_data():
            try:
                while True:
                    self._update_ui_data()
                    
                    # Update counters
                    if hasattr(self, '_refresh_counter'):
                        self._refresh_counter += 1
                    else:
                        self._refresh_counter = 0
                    
                    # Check for daily reset every 60 seconds (sufficient for midnight detection)
                    if self._refresh_counter % 60 == 0:
                        self._check_daily_reset()
                    
                    # Update lifetime stats display every 10 seconds
                    if self._refresh_counter % 10 == 0:  # Every 10 seconds
                        self._update_lifetime_stats_display()
                    
                    await asyncio.sleep(1.0)  # Update every 1 second for responsive timers
            except asyncio.CancelledError:
                print("Data refresh task cancelled")
                raise
            except Exception as e:
                print(f"Error in data refresh: {e}")
        
        self._data_refresh_task = asyncio.create_task(refresh_data())
    
    def _update_ui_data(self):
        """Update reactive UI data properties - this will automatically update bound UI elements"""
        # Update weight display
        drink_grams = self._get_drink_level_grams()
        drink_percent = self._get_drink_level_percent()
        daily_progress = (self.daily_consumed_ml / self.daily_goal_ml) * 100
        
        # Get hydration window info for display
        hydration_info = self._get_hydration_window_info()
        
        # Add urgency indicator to daily progress
        urgency_indicator = ""
        if hydration_info['urgency_factor'] > 2.0:
            urgency_indicator = " ⚠️ URGENT"
        elif hydration_info['urgency_factor'] > 1.0:
            urgency_indicator = " ⏰ High Priority"
        
        time_status = ""
        if hydration_info['time_status'] == "in_window":
            time_status = f" ({hydration_info['hours_remaining']:.1f}h left)"
        elif hydration_info['time_status'] == "after_window":
            time_status = " (after hours)"
        elif hydration_info['time_status'] == "before_window":
            time_status = " (before hours)"
        
        # Add dynamic reminder interval info
        current_interval = self._get_dynamic_reminder_interval()
        reminder_info = f" | Next reminder: {current_interval}min"
        
        self.ui_data['weight_display'] = f'Total: {self.current_weight}g | Drink: {drink_grams:.0f}g ({drink_percent:.1f}%) | Daily: {self.daily_consumed_ml:.0f}/{self.daily_goal_ml}ml ({daily_progress:.1f}%){time_status}{urgency_indicator}{reminder_info}'
        
        # Update status display - conditionally show orientation based on simulator mode
        status_parts = []
        
        if self.config.simulator_mode:
            orientation_status = "✅ Vertical" if self._is_bottle_vertical() else "⚠️ Tilted"
            status_parts.append(orientation_status)
        
        empty_status = "🚨 Empty" if self.is_empty_state else "💧 Has Drink"
        status_parts.append(empty_status)
        
        # Enhanced dehydration status with new dehydration level system
        dehydration_level = self._calculate_dehydration_level()
        
        if dehydration_level <= 0.5:
            if hydration_info['urgency_factor'] > 2.0:
                dehydration_status = f"💧 Well Hydrated but URGENT timing! (Level: {dehydration_level:.1f})"
            else:
                dehydration_status = f"💧 Well Hydrated (Level: {dehydration_level:.1f})"
        elif dehydration_level <= 1.2:
            if hydration_info['urgency_factor'] > 2.0:
                dehydration_status = f"💧 Mild Dehydration + URGENT! (Level: {dehydration_level:.1f})"
            else:
                dehydration_status = f"💧 Mild Dehydration (Level: {dehydration_level:.1f})"
        elif dehydration_level <= 2.0:
            if hydration_info['urgency_factor'] > 2.0:
                dehydration_status = f"⚠️ Moderate Dehydration + URGENT! (Level: {dehydration_level:.1f})"
            else:
                dehydration_status = f"⚠️ Moderate Dehydration (Level: {dehydration_level:.1f})"
        else:
            if hydration_info['urgency_factor'] > 2.0:
                dehydration_status = f"🚨 Severe Dehydration + URGENT! (Level: {dehydration_level:.1f})"
            else:
                dehydration_status = f"🚨 Severe Dehydration (Level: {dehydration_level:.1f})"
        
        status_parts.append(dehydration_status)
        self.ui_data['status_display'] = ' | '.join(status_parts)
        
        # Update event log
        recent_events = self.event_manager.events[-10:]
        log_text = ""
        for event in reversed(recent_events):
            time_str = event.timestamp.strftime("%H:%M:%S")
            if event.timer_name:
                log_text += f"[{time_str}] {event.timer_name}:{event.event_type} (#{event.severity})\n"
            else:
                log_text += f"[{time_str}] {event.event_type} (#{event.severity})\n"
        
        self.ui_data['event_log'] = log_text
        
        # Update timer status
        self.ui_data['timer_status'] = self._get_timer_status()
        
        # Update hydration status display
        dehydration_level = self._calculate_dehydration_level()
        hydration_factor = hydration_info['urgency_factor'] if hydration_info else 0.0
        
        # Simplified hydration status display - combine into one clear message
        if dehydration_level <= 0.5:
            status_emoji = "💧✨"
            status_text = "Well Hydrated"
        elif dehydration_level <= 1.2:
            status_emoji = "💧"
            status_text = "Mild Dehydration"
        elif dehydration_level <= 2.0:
            status_emoji = "⚠️"
            status_text = "Moderate Dehydration"
        else:
            status_emoji = "🚨"
            status_text = "Severe Dehydration"
        
        # Add urgency context if needed
        urgency_text = ""
        if hydration_factor > 2.0:
            urgency_text = " (URGENT!)"
        elif hydration_factor > 1.0:
            urgency_text = " (High Priority)"
        
        self.ui_data['hydration_status_display'] = f'{status_emoji} {status_text}{urgency_text} | Level: {dehydration_level:.1f}/3.0 | Daily: {self.daily_consumed_ml:.0f}/{self.daily_goal_ml}ml'
    
    def _setup_timers(self):
        """Setup all the application timers"""
        # Main drink reminder timer - start with base interval, will be adjusted dynamically
        self.timer_manager.add_timer(
            'drink_reminder',
            self.drink_reminder_base,  # Start with base interval
            self._drink_reminder_callback,
            self.random_threshold_minutes
        )
        
        # Bad orientation timer - start with base interval, will be adjusted dynamically
        self.timer_manager.add_timer(
            'bad_orientation',
            self.bad_orientation_base,
            self._bad_orientation_callback
        )
        
        # Empty reminder timer - start with base interval, will be adjusted dynamically
        self.timer_manager.add_timer(
            'empty_reminder',
            self.empty_reminder_base,
            self._empty_reminder_callback
        )
        
        # Recalibrate reminder timer
        self.timer_manager.add_timer(
            'recalibrate_reminder',
            self.recalibrate_reminder_days * 24 * 60,  # Convert days to minutes
            self._recalibrate_reminder_callback
        )
        
        # Initially deactivate some timers (this should happen after timers are added)
        self.timer_manager.deactivate_timer('bad_orientation')
        self.timer_manager.deactivate_timer('empty_reminder')
        
        # Save the initial state to ensure these timers stay deactivated
        self.timer_manager._save_timer_states()
    
    def _calculate_dehydration_level(self) -> float:
        """Calculate dehydration level based on actual hydration status over 24hr period.
        
        Returns:
            float: Dehydration level from 0.0 (perfectly hydrated) to 3.0 (severely dehydrated)
                   1.0 = mild dehydration (normal morning state)
                   2.0 = moderate dehydration  
                   3.0 = severe dehydration
        """
        # Get current hydration window info
        hydration_info = self._get_hydration_window_info()
        
        # Use local time for calculations
        from datetime import datetime
        current_time_local = datetime.now()  # Local time
        hours_since_start = 0
        
        # Calculate how many hours we've been in the hydration window today
        if hydration_info['time_status'] == "in_window":
            hours_since_start = current_time_local.hour - self.hydration_start_hour + (current_time_local.minute / 60.0)
        elif hydration_info['time_status'] == "after_window":
            hours_since_start = hydration_info['hours_in_window']  # Full hydration window has passed
        # If before_window, hours_since_start remains 0
        
        # Expected consumption based on reasonable rate (should have consumed this much by now)
        expected_ml = max(0, hours_since_start * self.reasonable_ml_per_hour)
        
        # Calculate hydration deficit as percentage of daily goal
        hydration_deficit = max(0, expected_ml - self.daily_consumed_ml)
        deficit_percent = hydration_deficit / self.daily_goal_ml if self.daily_goal_ml > 0 else 0
        
        # One-time debug to confirm the timezone fix
        if not hasattr(self, '_timezone_debug_shown'):
            self._timezone_debug_shown = True
            utc_time = time_service.get_accurate_time()
            print(f"🕐 TIMEZONE FIX APPLIED:")
            print(f"   UTC time: {utc_time}")
            print(f"   Local time: {current_time_local}")
            print(f"   Time status: {hydration_info['time_status']}")
            print(f"   Hours since hydration start: {hours_since_start:.2f}")
            print(f"   Expected ML: {expected_ml:.0f}")
            print(f"   Deficit: {hydration_deficit:.0f}")
        
        # Convert deficit to dehydration level
        # 0-10% deficit = 0.0-1.0 (well hydrated to mild dehydration)
        # 10-25% deficit = 1.0-2.0 (mild to moderate dehydration)  
        # 25%+ deficit = 2.0-3.0 (moderate to severe dehydration)
        if deficit_percent <= 0.1:  # 0-10% deficit
            dehydration_level = deficit_percent * 10  # 0.0 to 1.0
        elif deficit_percent <= 0.25:  # 10-25% deficit
            dehydration_level = 1.0 + ((deficit_percent - 0.1) / 0.15) * 1.0  # 1.0 to 2.0
        else:  # 25%+ deficit
            dehydration_level = min(3.0, 2.0 + ((deficit_percent - 0.25) / 0.25) * 1.0)  # 2.0 to 3.0
        
        return dehydration_level
    
    def _get_dynamic_reminder_interval(self) -> int:
        """Calculate dynamic reminder interval based on dehydration level.
        
        Returns:
            int: Reminder interval in minutes
        """
        dehydration_level = self._calculate_dehydration_level()
        
        # Linear interpolation between base and limit based on dehydration level
        # Level 0.0 (well hydrated) -> base interval (45 min)
        # Level 3.0 (severely dehydrated) -> limit interval (10 min)
        if dehydration_level <= 0:
            interval = self.drink_reminder_base
        elif dehydration_level >= 3.0:
            interval = self.drink_reminder_limit
        else:
            # Linear interpolation: interval = base - (base - limit) * (level / 3.0)
            interval_range = self.drink_reminder_base - self.drink_reminder_limit
            reduction = interval_range * (dehydration_level / 3.0)
            interval = self.drink_reminder_base - reduction
        
        # Ensure we stay within bounds and return integer
        return max(self.drink_reminder_limit, min(self.drink_reminder_base, int(interval)))
    
    def _get_dynamic_empty_reminder_interval(self) -> int:
        """Calculate dynamic interval for empty reminders based on how many have been ignored"""
        # Get count of empty reminders that have been ignored
        empty_reminder_count = self.event_manager.event_counts.get('empty_reminder:empty_reminder', 0)
        
        # Decrease interval as reminders are ignored (more urgent)
        # Base 10min -> 8min -> 6min -> 4min -> 2min (limit)
        interval_reduction = empty_reminder_count * 2  # 2 minutes per ignored reminder
        dynamic_interval = self.empty_reminder_base - interval_reduction
        
        return max(self.empty_reminder_limit, dynamic_interval)
    
    def _get_dynamic_bad_orientation_interval(self) -> int:
        """Calculate dynamic interval for bad orientation reminders based on how many have been ignored"""
        # Get count of bad orientation reminders that have been ignored
        bad_orientation_count = self.event_manager.event_counts.get('bad_orientation:bad_orientation', 0)
        
        # Decrease interval as reminders are ignored (more urgent)
        # Base 10min -> 8min -> 6min -> 4min -> 2min (limit)
        interval_reduction = bad_orientation_count * 2  # 2 minutes per ignored reminder
        dynamic_interval = self.bad_orientation_base - interval_reduction
        
        return max(self.bad_orientation_limit, dynamic_interval)
    
    def _update_reminder_timer_interval(self):
        """Update the drink reminder timer interval based on current dehydration level."""
        new_interval = self._get_dynamic_reminder_interval()
        
        # Update timer interval if it has changed
        if 'drink_reminder' in self.timer_manager.timers:
            current_timer = self.timer_manager.timers['drink_reminder']
            if current_timer.interval_minutes != new_interval:
                current_timer.interval_minutes = new_interval
                # Recalculate next trigger time based on new interval
                current_time = time_service.get_accurate_time()
                current_timer.next_trigger_time = self.timer_manager._calculate_next_trigger(current_timer, current_time)
                self.timer_manager._save_timer_states()
                print(f"🔄 Dynamic reminder interval updated to {new_interval} minutes (dehydration level: {self._calculate_dehydration_level():.1f})")
    
    def _update_empty_reminder_timer_interval(self):
        """Update the empty reminder timer interval based on how many reminders have been ignored."""
        new_interval = self._get_dynamic_empty_reminder_interval()
        
        # Update timer interval if it has changed
        if 'empty_reminder' in self.timer_manager.timers:
            current_timer = self.timer_manager.timers['empty_reminder']
            if current_timer.interval_minutes != new_interval:
                current_timer.interval_minutes = new_interval
                # Recalculate next trigger time based on new interval
                current_time = time_service.get_accurate_time()
                current_timer.next_trigger_time = self.timer_manager._calculate_next_trigger(current_timer, current_time)
                self.timer_manager._save_timer_states()
                print(f"🔄 Empty reminder interval updated to {new_interval} minutes (ignored count: {self.event_manager.event_counts.get('empty_reminder:empty_reminder', 0)})")
    
    def _update_bad_orientation_timer_interval(self):
        """Update the bad orientation timer interval based on how many reminders have been ignored."""
        new_interval = self._get_dynamic_bad_orientation_interval()
        
        # Update timer interval if it has changed
        if 'bad_orientation' in self.timer_manager.timers:
            current_timer = self.timer_manager.timers['bad_orientation']
            if current_timer.interval_minutes != new_interval:
                current_timer.interval_minutes = new_interval
                # Recalculate next trigger time based on new interval
                current_time = time_service.get_accurate_time()
                current_timer.next_trigger_time = self.timer_manager._calculate_next_trigger(current_timer, current_time)
                self.timer_manager._save_timer_states()
                print(f"🔄 Bad orientation interval updated to {new_interval} minutes (ignored count: {self.event_manager.event_counts.get('bad_orientation:bad_orientation', 0)})")
    
    async def initialize_app(self):
        """Initialize the application with time sync and storage"""
        # Prevent multiple initializations
        if hasattr(self, '_app_initialized') and self._app_initialized:
            print("⚠️ App already initialized, skipping duplicate initialization")
            return
        
        print("🚀 Starting app initialization...")
        
        try:
            # Sync time first (only if not recently synced)
            if not time_service.last_sync_time:
                print("🕐 Syncing time with API...")
                await time_service.sync_time()
            
            # Set app start time
            self.app_start_time = time_service.get_accurate_time()
            print(f"🚀 App started at: {self.app_start_time}")
            
            # FORCE daily reset check BEFORE any calculations to fix corrupted data
            print("🔍 Checking for daily reset...")
            self._check_daily_reset()
            
            # Initialize dehydration level based on current state AFTER potential reset
            self.dehydration_level = self._calculate_dehydration_level()
            
            # Initialize reminder window tracking
            if self.reminder_window_start is None:
                self.reminder_window_start = self.app_start_time
                self.cumulative_hif_window = []
            
            # Set up dynamic reminder interval
            self._update_reminder_timer_interval()
            
            print(f"💧 New Hydration System Initialized:")
            print(f"   📊 Daily goal: {self.daily_goal_ml}ml, Current progress: {self.daily_consumed_ml}ml")
            print(f"   ⏰ Hydration window: {self.hydration_start_hour:02d}:00-{self.hydration_end_hour:02d}:00 ({self.hydration_end_hour - self.hydration_start_hour}h)")
            print(f"   🧭 Target rate: {self.reasonable_ml_per_hour}ml/h")
            print(f"   🌊 Dehydration level: {self.dehydration_level:.1f} (0.0=hydrated, 3.0=severe)")
            print(f"   ⏰ Dynamic reminder interval: {self._get_dynamic_reminder_interval()}min (base: {self.drink_reminder_base}min, limit: {self.drink_reminder_limit}min)")
            
            # Check for unexpected shutdown from previous session
            self._check_unexpected_shutdown()
            
            # Setup signal handlers for graceful shutdown
            self._setup_signal_handlers()
            
            # Cleanup old logs
            storage.cleanup_old_logs(days=30)
            
            # Log app start event
            self.event_manager.trigger_event('app_started', {
                'start_time': self.app_start_time.isoformat(),
                'time_synced': time_service.last_sync_time is not None,
                'dehydration_level': self.dehydration_level,
                'dynamic_reminder_interval': self._get_dynamic_reminder_interval()
            })
            
            # Update lifetime stats for new session
            storage.update_lifetime_stats(new_session=True)
            
            print("✅ App initialization complete")
            self._app_initialized = True
            
        except Exception as e:
            print(f"❌ Error initializing app: {e}")
            # Continue with system time if API sync fails
            self.app_start_time = time_service.get_accurate_time()
            self._app_initialized = True
    
    def _check_unexpected_shutdown(self):
        """Check if the previous session ended unexpectedly"""
        try:
            app_state = storage.load_app_state()
            start_count = app_state.get('event_counts', {}).get('app_started', 0)
            shutdown_count = app_state.get('event_counts', {}).get('app_shutdown', 0)
            
            # If there are more starts than shutdowns, log unexpected shutdowns
            unexpected_shutdowns = start_count - shutdown_count
            if unexpected_shutdowns > 0:
                print(f"🚨 Detected {unexpected_shutdowns} unexpected shutdown(s) from previous sessions")
                # Log the missing shutdown events
                for i in range(unexpected_shutdowns):
                    self.event_manager.trigger_event('app_shutdown_unexpected', {
                        'detected_at_startup': self.app_start_time.isoformat(),
                        'reason': 'unexpected_exit_detected'
                    })
        except Exception as e:
            print(f"Error checking for unexpected shutdowns: {e}")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            print(f"📡 Received signal {signum}, initiating graceful shutdown...")
            # Schedule graceful shutdown
            asyncio.create_task(self._graceful_shutdown(f'signal_{signum}'))
        
        # Setup handlers for common termination signals
        try:
            signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
            signal.signal(signal.SIGTERM, signal_handler)  # Termination request
            if hasattr(signal, 'SIGHUP'):
                signal.signal(signal.SIGHUP, signal_handler)   # Hangup (Unix)
        except Exception as e:
            print(f"Warning: Could not setup signal handlers: {e}")
        
        # Also register atexit handler as backup
        atexit.register(self._atexit_handler)
    
    def _atexit_handler(self):
        """Atexit handler for emergency shutdown logging"""
        try:
            # Quick logging without async - this is emergency fallback
            if hasattr(self, 'event_manager') and self.event_manager:
                self.event_manager.trigger_event('app_shutdown_atexit', {
                    'shutdown_time': time_service.get_accurate_time().isoformat(),
                    'method': 'atexit_handler'
                })
        except Exception as e:
            print(f"Error in atexit handler: {e}")
    
    async def _graceful_shutdown(self, reason: str = 'unknown'):
        """Perform graceful shutdown with logging"""
        try:
            print(f"🔄 Graceful shutdown initiated: {reason}")
            
            # Log shutdown event
            self.event_manager.trigger_event('app_shutdown', {
                'shutdown_time': time_service.get_accurate_time().isoformat(),
                'reason': reason
            })
            
            # Save final state including bottle weight
            if self.app_start_time:
                storage.save_app_state(self.app_start_time, self.event_manager.event_counts, self.bottle_weight)
            
            # Cancel data refresh task
            if self._data_refresh_task and not self._data_refresh_task.done():
                self._data_refresh_task.cancel()
                try:
                    await asyncio.wait_for(self._data_refresh_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Stop timer manager
            await self.timer_manager.stop()
            print("✅ Graceful shutdown complete")
            
        except Exception as e:
            print(f"Error during graceful shutdown: {e}")
        finally:
            # Force exit if we're handling signals
            if reason.startswith('signal_'):
                os._exit(0)
    
    async def _drink_reminder_callback(self):
        """Main drink reminder callback - uses hydration status as severity"""
        # Update dehydration level based on actual hydration status
        self.dehydration_level = self._calculate_dehydration_level()
        
        # Start new reminder window for cumulative HIF tracking
        self.reminder_window_start = time_service.get_accurate_time()
        self.cumulative_hif_window = []  # Clear previous window drinks
        
        # Get hydration window info for urgency context
        hydration_info = self._get_hydration_window_info()
        
        # Calculate severity based on dehydration level, not reminder count
        dehydration_level = self.dehydration_level
        if dehydration_level >= 2.5:
            severity_desc = "SEVERE"
            urgency_emoji = "🚨"
            severity_level = 20 + min(int(dehydration_level * 5), 10)  # 20-30 range
        elif dehydration_level >= 1.5:
            severity_desc = "MODERATE" 
            urgency_emoji = "⚠️"
            severity_level = 10 + min(int(dehydration_level * 5), 10)  # 10-20 range
        elif dehydration_level >= 0.8:
            severity_desc = "MILD"
            urgency_emoji = "💧"
            severity_level = 5 + min(int(dehydration_level * 5), 5)  # 5-10 range
        else:
            severity_desc = "MINIMAL"
            urgency_emoji = "💧"
            severity_level = max(1, int(dehydration_level * 5))  # 1-5 range
        
        # Create more urgent reminder message if time is running out
        if hydration_info['urgency_factor'] > 2.0 and hydration_info['time_status'] == "in_window":
            reminder_message = f"{urgency_emoji} URGENT Drink Reminder! Only {hydration_info['hours_remaining']:.1f}h left! Need {hydration_info['remaining_ml_needed']:.0f}ml more! Dehydration: {severity_desc} ({dehydration_level:.1f})"
        elif hydration_info['urgency_factor'] > 1.0 and hydration_info['time_status'] == "in_window":
            reminder_message = f"{urgency_emoji} Priority Drink Reminder! {hydration_info['hours_remaining']:.1f}h remaining. Need {hydration_info['remaining_ml_needed']:.0f}ml. Dehydration: {severity_desc} ({dehydration_level:.1f})"
        elif hydration_info['time_status'] == "after_window":
            reminder_message = f"{urgency_emoji} Late Drink Reminder (after hydration hours). Dehydration: {severity_desc} ({dehydration_level:.1f})"
        elif hydration_info['time_status'] == "before_window":
            reminder_message = f"{urgency_emoji} Early Drink Reminder (before hydration hours). Dehydration: {severity_desc} ({dehydration_level:.1f})"
        else:
            reminder_message = f"{urgency_emoji} Drink Reminder! Dehydration: {severity_desc} ({dehydration_level:.1f})"
        
        event_data = {
            'dehydration_level': dehydration_level,
            'dehydration_severity': self.dehydration_severity,  # Legacy compatibility
            'hydration_window': hydration_info,
            'reminder_interval_minutes': self._get_dynamic_reminder_interval()
        }
        
        event = self.event_manager.trigger_event('drink_reminder', 
                                                timer_name='drink_reminder',
                                                data=event_data,
                                                custom_severity=severity_level)
        
        # Update reminder timer interval based on new dehydration level
        self._update_reminder_timer_interval()
        
        # Log message instead of showing toast from background task
        print(f"DRINK REMINDER: {reminder_message}")
    
    def _calculate_cumulative_hif(self, amount_consumed_ml: float) -> float:
        """Calculate cumulative hydration improvement factor based on amount consumed, dehydration severity, and time urgency."""
        # Base factor calculation
        if amount_consumed_ml <= 0:
            return 0.0
        
        # Get hydration window info for time-based urgency
        hydration_info = self._get_hydration_window_info()
        
        # Factor based on amount relative to daily goal
        amount_factor = min(amount_consumed_ml / (self.daily_goal_ml * 0.1), 1.0)  # 10% of daily goal = 1.0 factor
        
        # Factor based on dehydration severity (higher severity = higher factor potential)
        severity_multiplier = 1.0 + (self.dehydration_severity * 0.5)
        
        # Time urgency multiplier (higher urgency = higher factor potential)
        time_urgency = hydration_info['urgency_factor']
        time_multiplier = 1.0 + (time_urgency * 0.3)  # Up to 1.9x multiplier at max urgency
        
        # Calculate final factor (0.0 to 6.0 range with time urgency)
        improvement_factor = amount_factor * severity_multiplier * time_multiplier
        
        return min(improvement_factor, 6.0)
    
    def _clean_praise_window(self):
        """Clean old drinks from praise window"""
        current_time = time_service.get_accurate_time()
        cutoff_time = current_time - timedelta(minutes=self.praise_window_minutes)
        self.praise_window_drinks = [
            drink for drink in self.praise_window_drinks 
            if drink['timestamp'] > cutoff_time
        ]
    
    def _get_praise_message(self, amount_consumed_ml: float) -> tuple[str, str]:
        """Generate praise message based on amount consumed and recent intake"""
        # Clean old drinks from praise window
        self._clean_praise_window()
        
        # Add current drink to praise window
        current_time = time_service.get_accurate_time()
        self.praise_window_drinks.append({
            'amount_ml': amount_consumed_ml,
            'timestamp': current_time
        })
        
        # Calculate cumulative intake in praise window
        cumulative_ml = sum(drink['amount_ml'] for drink in self.praise_window_drinks)
        drink_count = len(self.praise_window_drinks)
        
        # Base praise based on current drink amount
        if amount_consumed_ml >= 300:
            base_praise = "Excellent hydration!"
            base_type = "positive"
        elif amount_consumed_ml >= 200:
            base_praise = "Great job drinking!"
            base_type = "positive"  
        elif amount_consumed_ml >= 100:
            base_praise = "Good hydration effort!"
            base_type = "info"
        elif amount_consumed_ml >= 50:
            base_praise = "Every drop counts, but you should be drinking more!"
            base_type = "info"
        else:
            base_praise = "Every sip helps, but aim for bigger drinks!"
            base_type = "warning"
        
        # Enhance praise for cumulative drinking in window
        if drink_count > 1:
            if cumulative_ml >= 400:
                cumulative_praise = f" Amazing! {cumulative_ml:.0f}ml in {self.praise_window_minutes:.0f} minute(s) - you're crushing it! 🏆"
                praise_type = "positive"
            elif cumulative_ml >= 250:
                cumulative_praise = f" Fantastic! {cumulative_ml:.0f}ml in {self.praise_window_minutes:.0f} minute(s) - keep it up! 💪"
                praise_type = "positive"
            elif cumulative_ml >= 150:
                cumulative_praise = f" Nice! {cumulative_ml:.0f}ml in {self.praise_window_minutes:.0f} minute(s) - great momentum! 🌊"
                praise_type = "info"
            else:
                cumulative_praise = f" {cumulative_ml:.0f}ml in {self.praise_window_minutes:.0f} minute(s) - good start, keep going!"
                praise_type = "info"
            
            return f"{base_praise}{cumulative_praise}", praise_type
        else:
            return base_praise, base_type
    
    def _get_hydration_message(self, amount_consumed_ml: float, improvement_factor: float) -> tuple[str, str]:
        """Generate appropriate hydration message based on consumption, improvement factor, and time urgency"""
        hydration_info = self._get_hydration_window_info()
        
        # Add time context to messages
        time_context = ""
        if hydration_info['time_status'] == "after_window":
            time_context = " (after hydration hours)"
        elif hydration_info['time_status'] == "before_window":
            time_context = " (before hydration hours)"
        elif hydration_info['urgency_factor'] > 2.0:
            time_context = f" (⚠️ {hydration_info['hours_remaining']:.1f}h left!)"
        elif hydration_info['urgency_factor'] > 1.0:
            time_context = f" ({hydration_info['hours_remaining']:.1f}h remaining)"
        
        # Get cumulative amount in this reminder window for more context
        total_window_amount = sum(drink['amount_ml'] for drink in self.cumulative_hif_window)
        window_drinks_count = len(self.cumulative_hif_window)
        
        # Add window context for cumulative drinking
        window_context = ""
        if window_drinks_count > 1:
            window_context = f" (Total this session: {total_window_amount:.0f}ml)"
        
        # Determine message type and content based on improvement factor
        if improvement_factor >= 4.0:
            # Very high improvement - excellent timing/amount
            message = f"🌟 Outstanding! {amount_consumed_ml:.0f}ml at perfect timing! 💪{time_context}{window_context}"
            message_type = "positive"
        elif improvement_factor >= 3.0:
            # High improvement - high praise
            message = f"🎉 Excellent! You drank {amount_consumed_ml:.0f}ml! Great hydration boost! 💪{time_context}{window_context}"
            message_type = "positive"
        elif improvement_factor >= 2.0:
            # Good improvement - moderate praise  
            message = f"👍 Good job! You drank {amount_consumed_ml:.0f}ml. Keep up the good hydration! 💧{time_context}{window_context}"
            message_type = "positive"
        elif improvement_factor >= 1.0:
            # Some improvement - encouragement
            message = f"✅ Nice! You drank {amount_consumed_ml:.0f}ml. Your body appreciates it! 🙂{time_context}{window_context}"
            message_type = "info"
        elif improvement_factor >= 0.5:
            # Small improvement - gentle encouragement (much more positive now with cumulative HIF)
            message = f"💧 You drank {amount_consumed_ml:.0f}ml. Every sip counts! Keep going! 😊{time_context}{window_context}"
            message_type = "info"
        else:
            # Very small improvement - still encouraging (less harsh than before)
            message = f"🚰 You drank {amount_consumed_ml:.0f}ml. Building good habits! 💪{time_context}{window_context}"
            message_type = "info"
        
        # Add urgency context for high urgency situations
        if hydration_info['urgency_factor'] > 2.0 and hydration_info['time_status'] == "in_window":
            if hydration_info['remaining_ml_needed'] > 0:
                message += f" Need {hydration_info['remaining_ml_needed']:.0f}ml more!"
        
        return message, message_type
    
    async def _handle_drink_event(self, amount_consumed_ml: float):
        """Handle a drink event with improved cumulative hydration improvement factor calculation"""
        if amount_consumed_ml <= 0:
            return
        
        # Get hydration window info for context
        hydration_info = self._get_hydration_window_info()
        
        # Calculate cumulative hydration improvement factor (new system)
        improvement_factor = self._calculate_cumulative_hif(amount_consumed_ml)
        
        # Update daily consumption
        self.daily_consumed_ml += amount_consumed_ml
        
        # Save daily consumption to storage
        storage.save_daily_consumption(self.daily_consumed_ml, self.last_daily_reset.isoformat())
        
        # Update lifetime stats
        storage.update_lifetime_stats(ml_consumed=amount_consumed_ml, drink_events=1)
        
        # Update dehydration level based on new consumption
        old_dehydration_level = self.dehydration_level
        self.dehydration_level = self._calculate_dehydration_level()
        
        # Legacy compatibility - reduce old dehydration severity based on improvement factor
        severity_reduction = max(1, int(improvement_factor))
        self.dehydration_severity = max(0, self.dehydration_severity - severity_reduction)
        
        # Get praise message based on amount and recent drinking
        message, message_type = self._get_praise_message(amount_consumed_ml)
        
        # Create drink event with rich data including new dehydration level system
        event_data = {
            'amount_ml': amount_consumed_ml,
            'improvement_factor': improvement_factor,
            'dehydration_level_before': old_dehydration_level,
            'dehydration_level_after': self.dehydration_level,
            'dehydration_severity_before': self.dehydration_severity + severity_reduction,  # Legacy
            'dehydration_severity_after': self.dehydration_severity,  # Legacy
            'daily_consumed_ml': self.daily_consumed_ml,
            'daily_goal_ml': self.daily_goal_ml,
            'daily_progress_percent': (self.daily_consumed_ml / self.daily_goal_ml) * 100,
            'hydration_window': hydration_info,
            'cumulative_window_amount': sum(drink['amount_ml'] for drink in self.cumulative_hif_window),
            'window_drinks_count': len(self.cumulative_hif_window)
        }
        
        # Trigger drink event
        event = self.event_manager.trigger_event('drink', data=event_data)
        
        # Reset drink reminder timer since they just drank
        self.timer_manager.reset_timer('drink_reminder')
        
        # Update reminder timer interval based on new dehydration level
        self._update_reminder_timer_interval()
        
        print(f"🔄 Drink reminder timer reset due to consumption of {amount_consumed_ml:.0f}ml (new dehydration level: {self.dehydration_level:.1f})")
        
        # Show hydration message
        await self._show_toast(f"{message} (Factor: {improvement_factor:.1f})", message_type)
        
        return event
    
    def _calculate_hydration_improvement_factor(self, amount_consumed_ml: float) -> float:
        """Calculate hydration improvement factor based on amount consumed, dehydration severity, and time urgency"""
        # DEPRECATED: This method is replaced by _calculate_cumulative_hif for better UX
        # Keeping for backward compatibility, but redirecting to new cumulative system
        return self._calculate_cumulative_hif(amount_consumed_ml)
    
    def _check_daily_reset(self):
        """Check if we need to reset daily consumption tracking"""
        # Use local time for daily reset checking
        from datetime import datetime
        current_date = datetime.now().date()
        
        if current_date != self.last_daily_reset:
            print(f"🌅 Daily reset triggered:")
            print(f"   Previous date: {self.last_daily_reset}")
            print(f"   Current date: {current_date}")
            print(f"   Daily consumption yesterday: {self.daily_consumed_ml}ml")
            
            # Update lifetime stats with yesterday's consumption before reset
            if self.daily_consumed_ml > 0:
                storage.update_lifetime_stats(ml_consumed=self.daily_consumed_ml, new_day=True)
                print(f"   Added {self.daily_consumed_ml}ml to lifetime stats")
            
            # Reset daily consumption
            self.daily_consumed_ml = 0
            self.last_daily_reset = current_date
            
            # Save the reset to storage
            storage.save_daily_consumption(self.daily_consumed_ml, self.last_daily_reset.isoformat())
            
            # Reset to mild dehydration (realistic morning state) instead of 0
            # Humans naturally become mildly dehydrated overnight
            self.dehydration_level = 1.0  # Mild dehydration at start of day
            self.dehydration_severity = 0  # Legacy system still resets to 0
            
            # Clear reminder window tracking for new day
            self.reminder_window_start = None
            self.cumulative_hif_window = []
            
            print(f"💧 Daily reset complete:")
            print(f"   Daily consumption: {self.daily_consumed_ml}ml")
            print(f"   Dehydration level: {self.dehydration_level}")
            print(f"   Last reset date: {self.last_daily_reset}")
    
    def _is_in_hydration_window(self) -> bool:
        """Check if current time is within active hydration window"""
        current_time = time_service.get_accurate_time()
        current_hour = current_time.hour
        
        if self.hydration_start_hour <= self.hydration_end_hour:
            # Normal case: 7am-10pm
            return self.hydration_start_hour <= current_hour < self.hydration_end_hour
        else:
            # Handles edge case if window crosses midnight (e.g., 22-6)
            return current_hour >= self.hydration_start_hour or current_hour < self.hydration_end_hour
    
    def _get_hydration_window_info(self) -> dict:
        """Get information about current hydration window and urgency"""
        # Use local time for hydration window calculations
        from datetime import datetime
        current_time_local = datetime.now()  # Local time
        current_hour = current_time_local.hour
        current_minute = current_time_local.minute
        
        # Initialize hours_remaining to ensure it's always defined
        hours_remaining = 0
        
        # Calculate time until end of hydration window
        if self.hydration_start_hour <= self.hydration_end_hour:
            # Normal case: 7am-10pm
            if current_hour < self.hydration_start_hour:
                # Before window starts
                hours_until_start = self.hydration_start_hour - current_hour
                hours_in_window = self.hydration_end_hour - self.hydration_start_hour
                time_status = "before_window"
                hours_remaining = hours_in_window  # Time available when window starts
            elif current_hour >= self.hydration_end_hour:
                # After window ends
                hours_remaining = 0
                hours_in_window = self.hydration_end_hour - self.hydration_start_hour
                time_status = "after_window"
            else:
                # During window
                hours_remaining = self.hydration_end_hour - current_hour - (current_minute / 60.0)
                hours_in_window = self.hydration_end_hour - self.hydration_start_hour
                time_status = "in_window"
        else:
            # Edge case: window crosses midnight
            hours_in_window = (24 - self.hydration_start_hour) + self.hydration_end_hour
            if current_hour >= self.hydration_start_hour:
                hours_remaining = (24 - current_hour) + self.hydration_end_hour - (current_minute / 60.0)
                time_status = "in_window"
            elif current_hour < self.hydration_end_hour:
                hours_remaining = self.hydration_end_hour - current_hour - (current_minute / 60.0)
                time_status = "in_window"
            else:
                hours_remaining = 0
                time_status = "after_window"
        
        # Calculate hydration urgency
        remaining_ml_needed = max(0, self.daily_goal_ml - self.daily_consumed_ml)
        
        if hours_remaining <= 0 or time_status == "after_window":
            urgency_factor = 0.0 if remaining_ml_needed == 0 else 5.0  # Max urgency if behind after window
            required_ml_per_hour = 0
        elif time_status == "before_window":
            urgency_factor = 0.0  # No urgency before hydration window
            required_ml_per_hour = remaining_ml_needed / hours_in_window
        else:
            required_ml_per_hour = remaining_ml_needed / hours_remaining if hours_remaining > 0 else 0
            urgency_factor = min(required_ml_per_hour / self.reasonable_ml_per_hour, 3.0)
        
        return {
            'time_status': time_status,
            'hours_remaining': max(0, hours_remaining),
            'hours_in_window': hours_in_window,
            'remaining_ml_needed': remaining_ml_needed,
            'required_ml_per_hour': required_ml_per_hour,
            'urgency_factor': urgency_factor,
            'progress_percent': (self.daily_consumed_ml / self.daily_goal_ml) * 100
        }
    
    async def _bad_orientation_callback(self):
        """Bad orientation reminder callback with dynamic interval adjustment"""
        if not self._is_bottle_vertical():
            event = self.event_manager.trigger_event('bad_orientation', timer_name='bad_orientation')
            
            # Update timer interval based on how many reminders have been ignored
            self._update_bad_orientation_timer_interval()
            
            # Log message instead of showing toast from background task
            print(f"BAD ORIENTATION: Warning #{event.severity} triggered at {event.timestamp}")
    
    async def _empty_reminder_callback(self):
        """Empty bottle reminder callback with dynamic interval adjustment"""
        if self.is_empty_state:
            event = self.event_manager.trigger_event('empty_reminder', timer_name='empty_reminder')
            
            # Update timer interval based on how many reminders have been ignored
            self._update_empty_reminder_timer_interval()
            
            # Log message instead of showing toast from background task
            print(f"EMPTY REMINDER: Warning #{event.severity} triggered at {event.timestamp}")
    
    async def _recalibrate_reminder_callback(self):
        """Recalibrate reminder callback"""
        # Check if very_empty event hasn't occurred in the last 2 days
        recent_very_empty = None
        for event in reversed(self.event_manager.events):
            if event.event_type == 'very_empty':
                if (datetime.now() - event.timestamp).days < self.recalibrate_reminder_days:
                    recent_very_empty = event
                break
        
        if not recent_very_empty:
            event = self.event_manager.trigger_event('recalibrate_reminder', timer_name='recalibrate_reminder')
            # Log message instead of showing toast from background task
            print(f"RECALIBRATE REMINDER: Reminder #{event.severity} triggered at {event.timestamp}")
    
    def _is_bottle_vertical(self) -> bool:
        """Check if bottle is within orientation threshold of vertical"""
        # Calculate angle from vertical (z-axis should be ~1 for vertical)
        z_normalized = abs(self.accelerometer['z'])
        angle_from_vertical = math.degrees(math.acos(min(1.0, z_normalized)))
        return angle_from_vertical <= self.orientation_threshold
    
    def _get_drink_level_grams(self) -> float:
        """Get the current drink level in grams (excluding bottle weight)"""
        return max(0, self.current_weight - self.bottle_weight)
    
    def _get_drink_level_percent(self) -> float:
        """Get the current drink level as percentage of max capacity"""
        max_drink = self.max_weight - self.bottle_weight
        current_drink = self._get_drink_level_grams()
        return (current_drink / max_drink) * 100 if max_drink > 0 else 0
    
    async def _show_toast(self, message: str, type_: str = 'info'):
        """Show a toast notification - safe for background tasks"""
        try:
            # Use NiceGUI notification system
            ui.notify(
                message, 
                type=type_, 
                position='top-right',
                timeout=5000,
                close_button=True
            )
        except RuntimeError as e:
            if "slot stack" in str(e):
                # Called from background task - just log to console
                print(f"TOAST [{type_.upper()}]: {message}")
            else:
                raise
    
    async def reset_session_data(self, preserve_lifetime_stats: bool = True):
        """Reset current session data while preserving lifetime statistics"""
        try:
            # Use storage reset function
            success = storage.reset_session_data(preserve_lifetime_stats)
            
            if success:
                # Reload data from storage after reset
                app_state = storage.load_app_state()
                self.daily_consumed_ml = app_state.get('daily_consumed_ml', 0.0)
                self.last_daily_reset = time_service.get_accurate_time().date()
                
                # Reset in-memory state
                self.dehydration_level = 1.0
                self.dehydration_severity = 0
                self.reminder_window_start = None
                self.cumulative_hif_window = []
                
                # Reload event manager with fresh data
                self.event_manager = EventManager()
                
                # Reset and restart timers
                self.timer_manager = TimerManager(self.min_timer_gap_minutes)
                self._setup_timers()
                
                await self._show_toast(f"✅ Session reset complete! {'Lifetime stats preserved' if preserve_lifetime_stats else 'All data reset'}", 'positive')
                print(f"🔄 Session data reset. Daily consumption: {self.daily_consumed_ml}ml")
                return True
            else:
                await self._show_toast("❌ Failed to reset session data", 'error')
                return False
                
        except Exception as e:
            print(f"❌ Error resetting session: {e}")
            await self._show_toast(f"❌ Reset error: {e}", 'error')
            return False
    
    def get_lifetime_stats(self) -> dict:
        """Get lifetime statistics"""
        app_state = storage.load_app_state()
        return app_state.get('lifetime_stats', {
            "total_sessions": 0,
            "total_ml_consumed": 0.0,
            "total_drink_events": 0,
            "days_tracked": 0
        })
    
    def _update_lifetime_stats_display(self):
        """Update the lifetime statistics display"""
        try:
            stats = self.get_lifetime_stats()
            stats_text = f"""
Sessions: {stats['total_sessions']}
Total Consumed: {stats['total_ml_consumed']:.0f}ml
Drink Events: {stats['total_drink_events']}
Days Tracked: {stats['days_tracked']}
Avg per Day: {stats['total_ml_consumed'] / max(1, stats['days_tracked']):.0f}ml
            """.strip()
            
            if hasattr(self, 'lifetime_stats_label'):
                self.lifetime_stats_label.text = stats_text
        except Exception as e:
            print(f"Error updating lifetime stats display: {e}")

    def _save_event_counts(self):
        """Save current event counts to storage"""
        try:
            current_time = time_service.get_accurate_time()
            storage.save_app_state(current_time, self.event_manager.event_counts, None, self.daily_consumed_ml, self.last_daily_reset.isoformat())  # Include daily consumption
        except Exception as e:
            print(f"Error saving event counts: {e}")
    
    async def _handle_weight_change(self):
        """Handle weight change and trigger appropriate events"""
        # Check for daily reset first
        self._check_daily_reset()
        
        weight_diff = self.current_weight - self.previous_weight
        drink_level = self._get_drink_level_grams()
        
        # Handle consumption (weight decreased)
        if weight_diff < 0:
            amount_consumed_ml = abs(weight_diff)  # 1g = 1ml for water
            if amount_consumed_ml >= 1:  # Only handle meaningful consumption
                await self._handle_drink_event(amount_consumed_ml)
        
        # Check for various events
        if drink_level <= self.very_empty_threshold:
            # Very empty - ask for confirmation
            await self._handle_very_empty()
        elif drink_level <= self.empty_threshold:
            # Empty but not very empty
            if not self.is_empty_state:
                self.is_empty_state = True
                event = self.event_manager.trigger_event('empty')
                await self._show_toast(f'📉 Bottle is empty! (#{event.severity})', 'warning')
                # Activate empty reminder timer
                self.timer_manager.activate_timer('empty_reminder')
                self.timer_manager.reset_timer('empty_reminder')
        else:
            # Not empty anymore
            if self.is_empty_state:
                self.is_empty_state = False
                self.timer_manager.deactivate_timer('empty_reminder')
                # Reset empty reminder count since issue is resolved
                self.event_manager.event_counts['empty_reminder:empty_reminder'] = 0
                # Reset the timer so it starts fresh when activated again
                self.timer_manager.reset_timer('empty_reminder')
                print("🔄 Empty reminder count reset and timer reset - bottle refilled")
        
        # Check for fill events (weight increased)
        if weight_diff > 0:
            max_capacity_threshold = (self.max_weight - self.bottle_weight) * (self.fill_threshold_percent / 100)
            current_from_max = (self.max_weight - self.current_weight)
            
            if current_from_max <= max_capacity_threshold:
                # Filled up to near max
                event = self.event_manager.trigger_event('filled_up')
                await self._show_toast(f'🌊 Bottle filled up! (#{event.severity})', 'positive')
            elif weight_diff <= self.drink_correction_threshold:
                # Small increase - drink correction
                event = self.event_manager.trigger_event('drink_correction', {'weight_diff': weight_diff})
                await self._show_toast(f'🔧 Drink correction: +{weight_diff:.1f}g (#{event.severity})', 'info')
            else:
                # Partial fill
                event = self.event_manager.trigger_event('partial_fill', {'weight_diff': weight_diff})
                await self._show_toast(f'💧 Partial fill: +{weight_diff:.1f}g (#{event.severity})', 'positive')
        
        # Check orientation and activate/deactivate bad orientation timer
        if not self._is_bottle_vertical():
            self.timer_manager.activate_timer('bad_orientation')
        else:
            was_timer_active = self.timer_manager.timers['bad_orientation'].is_active
            self.timer_manager.deactivate_timer('bad_orientation')
            if was_timer_active:
                # Reset bad orientation reminder count since issue is resolved
                self.event_manager.event_counts['bad_orientation:bad_orientation'] = 0
                # Reset the timer so it starts fresh when activated again
                self.timer_manager.reset_timer('bad_orientation')
        
        self.previous_weight = self.current_weight
        
        # Update dehydration level and dynamic reminder interval after any weight change
        old_dehydration_level = self.dehydration_level
        self.dehydration_level = self._calculate_dehydration_level()
        if abs(old_dehydration_level - self.dehydration_level) > 0.1:  # Only log significant changes
            print(f"🌊 Dehydration level updated: {old_dehydration_level:.1f} → {self.dehydration_level:.1f}")
        self._update_reminder_timer_interval()
        

    
    async def _handle_very_empty(self):
        """Handle very empty state with user confirmation"""
        result = await ui.run_javascript('''
            return confirm("Bottle appears to be completely empty. Recalibrate bottle weight?");
        ''')
        
        if result:
            # Recalibrate - set current weight as new bottle weight
            self.bottle_weight = self.current_weight
            self.is_empty_state = True
            
            # Save the new bottle weight to persistent storage
            storage.save_bottle_weight(self.bottle_weight)
            print(f"🔧 Bottle weight recalibrated and saved: {self.bottle_weight}g")
            
            event = self.event_manager.trigger_event('very_empty_recalibrated', {'new_bottle_weight': self.bottle_weight})
            await self._show_toast(f'🔧 Recalibrated! New bottle weight: {self.bottle_weight}g (#{event.severity})', 'positive')
            # Reset recalibrate timer
            self.timer_manager.reset_timer('recalibrate_reminder')
        else:
            event = self.event_manager.trigger_event('very_empty')
            await self._show_toast(f'📉 Bottle very empty! (#{event.severity})', 'negative')
    
    async def on_weight_change(self, event=None):
        """Callback for weight slider change"""
        # Get value from event args or slider directly
        if event and hasattr(event, 'args') and event.args:
            self.current_weight = float(event.args)
        else:
            self.current_weight = self.weight_slider.value
        
        # print(f"Weight changed to: {self.current_weight}g")
    
    async def on_submit_weight(self):
        """Callback for submit button"""
        print(f"Submit weight: Previous={self.previous_weight}g, Current={self.current_weight}g")
        await self._handle_weight_change()
    
    async def on_accelerometer_change(self, event=None):
        """Callback for accelerometer changes"""
        # Check orientation and activate/deactivate bad orientation timer based on current orientation
        is_vertical = self._is_bottle_vertical()
        was_timer_active = self.timer_manager.timers['bad_orientation'].is_active
        
        if not is_vertical:
            self.timer_manager.activate_timer('bad_orientation')
            if not was_timer_active:  # Only log when status changes
                print(f"🔄 Bottle tilted (z={self.accelerometer['z']:.1f}) - bad orientation timer activated")
        else:
            self.timer_manager.deactivate_timer('bad_orientation')
            if was_timer_active:  # Only log when status changes
                # Reset bad orientation reminder count since issue is resolved
                self.event_manager.event_counts['bad_orientation:bad_orientation'] = 0
                # Reset the timer so it starts fresh when activated again
                self.timer_manager.reset_timer('bad_orientation')
                print(f"🔄 Bottle vertical (z={self.accelerometer['z']:.1f}) - bad orientation timer deactivated and reset, count reset") 
        
        # Update timer panel to reflect any activation changes
        await self._update_timer_panel()
    
    def _reset_axis(self, axis: str, value: float, slider):
        """Reset a single accelerometer axis to default value"""
        self.accelerometer[axis] = value
        slider.value = value
        # Force update the slider binding and then trigger change
        slider.update()
        asyncio.create_task(self.on_accelerometer_change())
    
    def _reset_all_axes(self, x_slider, y_slider, z_slider):
        """Reset all accelerometer axes to vertical position (default)"""
        self.accelerometer['x'] = 0
        self.accelerometer['y'] = 0
        self.accelerometer['z'] = 1
        x_slider.value = 0
        y_slider.value = 0
        z_slider.value = 1
        # Force update all sliders
        x_slider.update()
        y_slider.update()
        z_slider.update()
        asyncio.create_task(self.on_accelerometer_change())
    
    def _get_timer_status(self):
        """Get current timer status for UI display"""
        timer_status = []
        current_time = time_service.get_accurate_time()
        
        for name, timer in self.timer_manager.timers.items():
            # Skip simulator-only timers if simulator mode is disabled
            if not self.config.simulator_mode and name in ['bad_orientation', 'empty_reminder']:
                continue
                
            status = "🟢 ACTIVE" if timer.is_active else "🔴 INACTIVE"
            
            if timer.next_trigger_time and timer.is_active:
                time_diff = timer.next_trigger_time - current_time
                if time_diff.total_seconds() > 0:
                    total_seconds = int(time_diff.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    
                    if hours > 0:
                        countdown = f"{hours}h {minutes}m {seconds}s"
                    elif minutes > 0:
                        countdown = f"{minutes}m {seconds}s"
                    else:
                        countdown = f"{seconds}s"
                else:
                    countdown = "⚠️ OVERDUE"
            else:
                countdown = "INACTIVE" if not timer.is_active else "NOT SET"
            
            # Calculate current severity for this timer
            if name == 'drink_reminder':
                # For drink reminders, severity is based on hydration level
                dehydration_level = self._calculate_dehydration_level()
                if dehydration_level >= 2.5:
                    severity = 20 + min(int(dehydration_level * 5), 10)  # 20-30 range
                    severity_display = f"🚨 {severity}"
                elif dehydration_level >= 1.5:
                    severity = 10 + min(int(dehydration_level * 5), 10)  # 10-20 range
                    severity_display = f"⚠️ {severity}"
                elif dehydration_level >= 0.8:
                    severity = 5 + min(int(dehydration_level * 5), 5)  # 5-10 range
                    severity_display = f"💧 {severity}"
                else:
                    severity = max(1, int(dehydration_level * 5))  # 1-5 range
                    severity_display = f"💧 {severity}"
            else:
                # For other timers, severity is based on ignored count
                count_key = f"{name}:{name}"
                current_count = self.event_manager.event_counts.get(count_key, 0)
                if current_count == 0:
                    severity_display = "-"
                elif current_count >= 10:
                    severity_display = f"🚨 {current_count}"
                elif current_count >= 5:
                    severity_display = f"⚠️ {current_count}"
                else:
                    severity_display = f"📊 {current_count}"
            
            timer_status.append({
                'name': name.replace('_', ' ').title(),
                'status': status,
                'interval': f"{timer.interval_minutes}m",
                'countdown': countdown,
                'next_trigger': timer.next_trigger_time.strftime('%H:%M:%S') if timer.next_trigger_time else "N/A",
                'severity': severity_display
            })
        
        return timer_status
    
    async def _update_timer_panel(self):
        """Update the timer panel display"""
        try:
            if hasattr(self, 'timer_rows') and self.timer_rows:
                timer_status = self._get_timer_status()
                
                # Update each row
                for i, status in enumerate(timer_status):
                    if i < len(self.timer_rows):
                        row = self.timer_rows[i]
                        row['name'].text = status['name']
                        row['status'].text = status['status']
                        row['interval'].text = status['interval']
                        row['countdown'].text = status['countdown']
                        row['severity'].text = status['severity']
                        row['next_trigger'].text = status['next_trigger']
            else:
                print("Warning: timer_rows not available yet")
        except Exception as e:
            print(f"Error updating timer panel: {e}")
            
    def create_settings_modal(self):
        """Create the settings configuration modal"""
        with ui.dialog() as settings_dialog, ui.card().classes('w-full max-w-4xl mx-auto p-6'):
            ui.label('⚙️ Configuration Settings').classes('text-2xl font-bold mb-6')
            
            # Store current config values for the modal
            current_config = {}
            
            with ui.column().classes('w-full gap-4'):
                # UI Configuration Section
                with ui.expansion('🖥️ UI Configuration', icon='display_settings').classes('w-full'):
                    with ui.column().classes('gap-4 p-4'):
                        simulator_mode_switch = ui.switch('Simulator Mode', 
                                                        value=self.config.simulator_mode).classes('mb-2')
                        ui.label('When disabled, hides accelerometer controls and related features from the UI').classes('text-sm text-gray-600')
                        current_config['simulator_mode'] = simulator_mode_switch
                
                # Bottle Weight Configuration Section
                with ui.expansion('⚖️ Bottle Weight Configuration', icon='scale').classes('w-full'):
                    with ui.column().classes('gap-4 p-4'):
                        with ui.row().classes('w-full gap-4'):
                            with ui.column().classes('flex-1'):
                                ui.label('Empty Bottle Weight (g)').classes('text-sm font-medium mb-1')
                                empty_weight_input = ui.number(value=self.config.empty_bottle_weight,
                                                             min=100, max=2000, step=1).classes('w-full')
                            with ui.column().classes('flex-1'):
                                ui.label('Full Bottle Weight (g)').classes('text-sm font-medium mb-1')
                                full_weight_input = ui.number(value=self.config.full_bottle_weight,
                                                            min=500, max=3000, step=1).classes('w-full')
                        current_config['empty_bottle_weight'] = empty_weight_input
                        current_config['full_bottle_weight'] = full_weight_input
                
                # Daily Hydration Goals Section
                with ui.expansion('💧 Daily Hydration Goals', icon='local_drink').classes('w-full'):
                    with ui.column().classes('gap-4 p-4'):
                        with ui.row().classes('w-full gap-4'):
                            with ui.column().classes('flex-1'):
                                ui.label('Daily Goal (ml)').classes('text-sm font-medium mb-1')
                                daily_goal_input = ui.number(value=self.config.daily_goal_ml,
                                                           min=1000, max=5000, step=100).classes('w-full')
                            with ui.column().classes('flex-1'):
                                ui.label('Target Rate (ml/hour)').classes('text-sm font-medium mb-1')
                                reasonable_rate_input = ui.number(value=self.config.reasonable_ml_per_hour,
                                                                min=50, max=300, step=10).classes('w-full')
                        with ui.row().classes('w-full gap-4'):
                            with ui.column().classes('flex-1'):
                                ui.label('Hydration Start Hour (24h)').classes('text-sm font-medium mb-1')
                                start_hour_input = ui.number(value=self.config.hydration_start_hour,
                                                           min=0, max=23, step=1).classes('w-full')
                            with ui.column().classes('flex-1'):
                                ui.label('Hydration End Hour (24h)').classes('text-sm font-medium mb-1')
                                end_hour_input = ui.number(value=self.config.hydration_end_hour,
                                                         min=1, max=24, step=1).classes('w-full')
                        current_config['daily_goal_ml'] = daily_goal_input
                        current_config['reasonable_ml_per_hour'] = reasonable_rate_input
                        current_config['hydration_start_hour'] = start_hour_input
                        current_config['hydration_end_hour'] = end_hour_input
                
                # Timer Configuration Section
                with ui.expansion('⏰ Timer Configuration', icon='timer').classes('w-full'):
                    with ui.column().classes('gap-4 p-4'):
                        ui.label('Drink Reminder Timer (Dynamic)').classes('font-semibold')
                        with ui.row().classes('w-full gap-4'):
                            with ui.column().classes('flex-1'):
                                ui.label('Base Interval (min)').classes('text-sm font-medium mb-1')
                                drink_base_input = ui.number(value=self.config.drink_reminder_base,
                                                           min=15, max=120, step=5).classes('w-full')
                            with ui.column().classes('flex-1'):
                                ui.label('Urgent Limit (min)').classes('text-sm font-medium mb-1')
                                drink_limit_input = ui.number(value=self.config.drink_reminder_limit,
                                                            min=5, max=60, step=5).classes('w-full')
                        
                        ui.separator().classes('my-4')
                        
                        with ui.row().classes('w-full gap-4'):
                            with ui.column().classes('flex-1'):
                                ui.label('Random Threshold (min)').classes('text-sm font-medium mb-1')
                                random_threshold_input = ui.number(value=self.config.random_threshold_minutes,
                                                                 min=0, max=15, step=1).classes('w-full')
                            with ui.column().classes('flex-1'):
                                ui.label('Min Timer Gap (min)').classes('text-sm font-medium mb-1')
                                min_gap_input = ui.number(value=self.config.min_timer_gap_minutes,
                                                        min=1, max=10, step=1).classes('w-full')
                        
                        current_config['drink_reminder_base'] = drink_base_input
                        current_config['drink_reminder_limit'] = drink_limit_input
                        current_config['random_threshold_minutes'] = random_threshold_input
                        current_config['min_timer_gap_minutes'] = min_gap_input
                
                # Thresholds Configuration Section
                with ui.expansion('🚨 Detection Thresholds', icon='warning').classes('w-full'):
                    with ui.column().classes('gap-4 p-4'):
                        with ui.row().classes('w-full gap-4'):
                            with ui.column().classes('flex-1'):
                                ui.label('Empty Threshold (g)').classes('text-sm font-medium mb-1')
                                empty_threshold_input = ui.number(value=self.config.empty_threshold,
                                                                min=10, max=200, step=5).classes('w-full')
                            with ui.column().classes('flex-1'):
                                ui.label('Very Empty Threshold (g)').classes('text-sm font-medium mb-1')
                                very_empty_input = ui.number(value=self.config.very_empty_threshold,
                                                           min=1, max=50, step=1).classes('w-full')
                        with ui.row().classes('w-full gap-4'):
                            with ui.column().classes('flex-1'):
                                ui.label('Orientation Threshold (degrees)').classes('text-sm font-medium mb-1')
                                orientation_input = ui.number(value=self.config.orientation_threshold,
                                                            min=5, max=45, step=5).classes('w-full')
                            with ui.column().classes('flex-1'):
                                ui.label('Fill Threshold (%)').classes('text-sm font-medium mb-1')
                                fill_percent_input = ui.number(value=self.config.fill_threshold_percent,
                                                             min=5, max=25, step=5).classes('w-full')
                        
                        current_config['empty_threshold'] = empty_threshold_input
                        current_config['very_empty_threshold'] = very_empty_input
                        current_config['orientation_threshold'] = orientation_input
                        current_config['fill_threshold_percent'] = fill_percent_input
                
                # Reset Options Section (moved from Status)
                with ui.expansion('🔄 Reset Options', icon='refresh').classes('w-full'):
                    with ui.column().classes('gap-4 p-4'):
                        ui.label('Reset current session data:').classes('text-sm mb-2')
                        with ui.row().classes('w-full gap-2'):
                            ui.button('Reset Session (Keep Lifetime Stats)', 
                                     on_click=lambda: asyncio.create_task(self.reset_session_data(preserve_lifetime_stats=True))
                                     ).classes('flex-1 bg-orange-500')
                            ui.button('Complete Reset (All Data)', 
                                     on_click=lambda: asyncio.create_task(self.reset_session_data(preserve_lifetime_stats=False))
                                     ).classes('flex-1 bg-red-600')
                        ui.label('⚠️ Use reset if you notice incorrect hydration levels or accumulated errors.').classes('text-xs text-gray-500 mt-2')
            
            # Modal buttons
            with ui.row().classes('w-full justify-end gap-4 mt-6'):
                ui.button('Cancel', on_click=settings_dialog.close).classes('bg-gray-500')
                
                async def save_settings():
                    try:
                        # Collect all config values
                        new_config = {}
                        for key, input_element in current_config.items():
                            new_config[key] = input_element.value
                        
                        # Update configuration
                        success = self.update_config_from_ui(new_config)
                        
                        if success:
                            await self._show_toast('✅ Configuration saved successfully!', 'positive')
                            settings_dialog.close()
                            
                            # Refresh UI if simulator mode changed
                            if 'simulator_mode' in new_config:
                                await self._update_simulator_mode_visibility()
                        else:
                            await self._show_toast('❌ Failed to save configuration', 'negative')
                    except Exception as e:
                        await self._show_toast(f'❌ Error saving settings: {e}', 'negative')
                
                ui.button('Save', on_click=save_settings).classes('bg-blue-600')
        
        return settings_dialog
    
    async def _update_simulator_mode_visibility(self):
        """Update visibility of simulator mode elements"""
        try:
            is_simulator = self.config.simulator_mode
            
            # Update accelerometer card visibility
            if hasattr(self, 'accelerometer_card'):
                if is_simulator:
                    self.accelerometer_card.style('display: block')
                else:
                    self.accelerometer_card.style('display: none')
            
            # Update app title
            if hasattr(self, 'app_title_label'):
                app_title = '🍺 Drink Reminder Simulator' if is_simulator else '🍺 Drink Reminder'
                self.app_title_label.text = app_title
            
            # Update page title using JavaScript since ui.page_title() doesn't work dynamically
            await ui.run_javascript(f'document.title = "{("Drink Reminder Simulator" if is_simulator else "Drink Reminder")}"')
            
            # Force update UI data to refresh status display
            self._update_ui_data()
            
            # Force update timer panel to show/hide simulator timers
            await self._update_timer_panel()
            
            print(f"🔄 Simulator mode visibility updated: {is_simulator}")
        except Exception as e:
            print(f"Error updating simulator mode visibility: {e}")



    def create_ui(self):
        """Create the main UI"""
        # Set initial page title based on simulator mode
        page_title = 'Drink Reminder Simulator' if self.config.simulator_mode else 'Drink Reminder'
        ui.page_title(page_title)
        
        with ui.card().classes('w-full max-w-6xl mx-auto p-6'):
            # Header with settings button
            with ui.row().classes('w-full items-center justify-between mb-6'):
                # Make app title reactive to simulator mode
                app_title = '🍺 Drink Reminder Simulator' if self.config.simulator_mode else '🍺 Drink Reminder'
                self.app_title_label = ui.label(app_title).classes('text-3xl font-bold')
                
                # Settings button
                settings_dialog = self.create_settings_modal()
                ui.button('⚙️', on_click=settings_dialog.open).props('flat round size=md').classes('ml-auto')
            
            # Responsive two-column layout
            with ui.row().classes('w-full gap-6'):
                # Left Column - Controls
                with ui.column().classes('flex-1 min-w-0'):
                    # Weight Controls
                    with ui.card().classes('mb-4 p-4'):
                        ui.label('💧 Bottle Weight Control').classes('text-xl font-semibold mb-4')
                        
                        self.weight_slider = ui.slider(
                            min=self.min_weight, 
                            max=self.max_weight, 
                            value=self.current_weight, 
                            step=1
                        ).props('label-always').classes('mb-4')
                        
                        # Use proper event binding that passes the value
                        self.weight_slider.on('update:model-value', lambda e: asyncio.create_task(self.on_weight_change(e)))
                        
                        ui.button('Submit Weight Change', on_click=self.on_submit_weight).classes('mb-4 w-full')
                        
                        # Bind weight display to reactive data
                        self.weight_display = ui.label().classes('text-lg font-mono')
                        self.weight_display.bind_text_from(self.ui_data, 'weight_display')
                    
                    # Accelerometer Controls (conditionally shown based on simulator mode)
                    self.accelerometer_card = ui.card().classes('mb-4 p-4')
                    with self.accelerometer_card:
                        ui.label('📱 Accelerometer Orientation').classes('text-xl font-semibold mb-4')
                        
                        # X-Axis Control
                        with ui.column().classes('mb-4'):
                            ui.label('X-Axis (Side to Side)').classes('font-medium text-gray-700 mb-2')
                            x_slider = ui.slider(min=-1, max=1, value=0, step=0.1).props('label-always').classes('mb-2')
                            x_slider.bind_value_to(self.accelerometer, 'x')
                            x_slider.on('update:model-value', lambda e: asyncio.create_task(self.on_accelerometer_change(e)))
                            
                            with ui.row().classes('gap-2 items-center'):
                                ui.label('Left: -1.0').classes('text-xs text-gray-500 flex-1')
                                ui.button('Reset', on_click=lambda: self._reset_axis('x', 0, x_slider)).props('size=sm').classes('bg-gray-400')
                                ui.label('Right: +1.0').classes('text-xs text-gray-500 flex-1 text-right')
                        
                        # Y-Axis Control
                        with ui.column().classes('mb-4'):
                            ui.label('Y-Axis (Forward/Backward)').classes('font-medium text-gray-700 mb-2')
                            y_slider = ui.slider(min=-1, max=1, value=0, step=0.1).props('label-always').classes('mb-2')
                            y_slider.bind_value_to(self.accelerometer, 'y')
                            y_slider.on('update:model-value', lambda e: asyncio.create_task(self.on_accelerometer_change(e)))
                            
                            with ui.row().classes('gap-2 items-center'):
                                ui.label('Back: -1.0').classes('text-xs text-gray-500 flex-1')
                                ui.button('Reset', on_click=lambda: self._reset_axis('y', 0, y_slider)).props('size=sm').classes('bg-gray-400')
                                ui.label('Forward: +1.0').classes('text-xs text-gray-500 flex-1 text-right')
                        
                        # Z-Axis Control
                        with ui.column().classes('mb-4'):
                            ui.label('Z-Axis (Up/Down - Gravity)').classes('font-medium text-gray-700 mb-2')
                            z_slider = ui.slider(min=-1, max=1, value=1, step=0.1).props('label-always').classes('mb-2')
                            z_slider.bind_value_to(self.accelerometer, 'z')
                            z_slider.on('update:model-value', lambda e: asyncio.create_task(self.on_accelerometer_change(e)))
                            
                            with ui.row().classes('gap-2 items-center'):
                                ui.label('Down: -1.0').classes('text-xs text-gray-500 flex-1')
                                ui.button('Reset', on_click=lambda: self._reset_axis('z', 1, z_slider)).props('size=sm').classes('bg-gray-400')
                                ui.label('Up: +1.0').classes('text-xs text-gray-500 flex-1 text-right')
                        
                        # Reset All Button
                        ui.button('Reset All to Vertical', on_click=lambda: self._reset_all_axes(x_slider, y_slider, z_slider)).classes('w-full mt-2 bg-blue-500')
                    
                    # Apply simulator mode visibility
                    if not self.config.simulator_mode:
                        self.accelerometer_card.style('display: none')
                
                # Right Column - Status and Events
                with ui.column().classes('flex-1 min-w-0'):
                    # Status Display
                    with ui.card().classes('mb-4 p-4'):
                        ui.label('📊 Status').classes('text-xl font-semibold mb-4')
                        # Bind status display to reactive data
                        self.status_display = ui.label().classes('text-lg mb-3')
                        self.status_display.bind_text_from(self.ui_data, 'status_display')
                        
                        # Hydration Status Scale
                        ui.label('💧 Hydration Status').classes('text-lg font-semibold mb-2')
                        self.hydration_status_display = ui.label().classes('text-md')
                        self.hydration_status_display.bind_text_from(self.ui_data, 'hydration_status_display')
                        
                        # Lifetime Stats (if available)
                        with ui.expansion('📊 Lifetime Statistics', icon='analytics').classes('w-full mt-4'):
                            self.lifetime_stats_label = ui.label().classes('text-sm')
                            self._update_lifetime_stats_display()
                    
                    # Timer Panel
                    with ui.card().classes('mb-4 p-4'):
                        with ui.row().classes('w-full items-center justify-between mb-4'):
                            ui.label('⏰ Timer Status').classes('text-xl font-semibold')
                            ui.button('🔄', on_click=lambda: asyncio.create_task(self._update_timer_panel())).props('flat round size=sm').classes('ml-auto')
                        
                        # Timer table header
                        with ui.row().classes('w-full gap-2 mb-2 text-sm font-semibold text-gray-600'):
                            ui.label('Timer').classes('flex-1')
                            ui.label('Status').classes('w-20')
                            ui.label('Interval').classes('w-16')
                            ui.label('Countdown').classes('w-24')
                            ui.label('Severity').classes('w-16')
                            ui.label('Next').classes('w-16')
                        
                        ui.separator()
                        
                        # Timer rows
                        self.timer_rows = []
                        for _ in range(4):  # Pre-create rows for the 4 timers
                            with ui.row().classes('w-full gap-2 py-1 text-sm'):
                                name_label = ui.label('').classes('flex-1 font-medium')
                                status_label = ui.label('').classes('w-20')
                                interval_label = ui.label('').classes('w-16')
                                countdown_label = ui.label('').classes('w-24 font-mono')
                                severity_label = ui.label('').classes('w-16 text-center')
                                next_label = ui.label('').classes('w-16 font-mono text-xs')
                                
                                self.timer_rows.append({
                                    'name': name_label,
                                    'status': status_label,
                                    'interval': interval_label,
                                    'countdown': countdown_label,
                                    'severity': severity_label,
                                    'next_trigger': next_label
                                })
                    
                    # Event Log
                    with ui.card().classes('p-4'):
                        ui.label('📋 Event Log').classes('text-xl font-semibold mb-4')
                        # Bind event log to reactive data
                        self.event_log = ui.textarea().classes('w-full mb-4').props('readonly rows=8')
                        self.event_log.bind_value_from(self.ui_data, 'event_log')
                        
                        with ui.row().classes('gap-2 w-full'):
                            async def clear_events():
                                self.event_manager.clear_events()
                            
                            ui.button('Clear Events', on_click=clear_events).classes('bg-red-500 flex-1')
                            
                            async def test_drink_reminder():
                                await self._drink_reminder_callback()
                                # Timer panel will update automatically via periodic refresh
                                await self._update_timer_panel()
                            
                            ui.button('Test Drink Reminder', on_click=test_drink_reminder).classes('bg-blue-500 flex-1')
        
        print("Info: UI elements created, reactive system will handle updates")
        
        # Initialize app (time sync, etc.) after UI is ready
        asyncio.create_task(self.initialize_app())
        
        # Immediate timer panel update
        print("Info: Scheduling immediate timer panel update")
        asyncio.create_task(self._update_timer_panel())
        
        # Start timer panel updates with real-time refresh (every 2 seconds)
        async def delayed_timer_setup():
            await asyncio.sleep(2)  # Wait for app initialization
            print("Info: Running delayed timer setup")
            await self._update_timer_panel()
        
        asyncio.create_task(delayed_timer_setup())
        
        # Create the auto-refresh timer in the main UI context (every 1 second for real-time updates)
        ui.timer(1.0, callback=lambda: asyncio.create_task(self._update_timer_panel()))
        
        # Start the data refresh task now that the UI context is available
        self._start_data_refresh_task()

# Global app instance
drink_app = DrinkReminderApp()

@ui.page('/')
async def index():
    drink_app.create_ui()

# Startup and shutdown handlers
async def on_startup():
    """App startup handler"""
    try:
        # Start timer manager after initialization
        await drink_app.timer_manager.start()
        print("Timer manager started")
    except Exception as e:
        print(f"Error starting timer manager: {e}")

async def on_shutdown():
    """App shutdown handler"""
    try:
        # Save final state including bottle weight
        if drink_app.app_start_time:
            storage.save_app_state(drink_app.app_start_time, drink_app.event_manager.event_counts, drink_app.bottle_weight)
        
        # Log shutdown event
        drink_app.event_manager.trigger_event('app_shutdown', {
            'shutdown_time': time_service.get_accurate_time().isoformat()
        })
        
        # Stop timer manager
        await drink_app.timer_manager.stop()
        print("App shutdown complete")
    except Exception as e:
        print(f"Error during shutdown: {e}")

app.on_startup(on_startup)
app.on_shutdown(on_shutdown)

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='Drink Reminder Simulator',
        port=8080,
        show=True,
        reload=False
    ) 