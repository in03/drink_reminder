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

class DrinkReminderApp:
    def __init__(self):
        # Configuration from .env
        self.reminder_timer_minutes = int(os.getenv('REMINDER_TIMER_MINUTES', 45))
        self.random_threshold_minutes = int(os.getenv('RANDOM_THRESHOLD_MINUTES', 5))
        self.min_weight = int(os.getenv('MIN_WEIGHT', 710))
        self.max_weight = int(os.getenv('MAX_WEIGHT', 1810))
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
        
        # Application state
        self.current_weight = self.max_weight  # Start with full bottle
        self.previous_weight = self.current_weight
        self.bottle_weight = self.min_weight  # Tare weight
        self.accelerometer = {'x': 0, 'y': 0, 'z': 1}  # Start vertical (gravity down)
        self.is_empty_state = False
        
        # Hydration tracking state
        self.dehydration_severity = 0  # Severity based on missed reminders
        self.daily_consumed_ml = 0  # Track daily consumption
        self.last_daily_reset = time_service.get_accurate_time().date()  # For daily reset
        
        # Event and timer managers
        self.event_manager = EventManager()
        self.timer_manager = TimerManager(self.min_timer_gap_minutes)
        
        # UI update queue for background tasks
        self.ui_update_queue = asyncio.Queue()
        
        # UI elements (will be set during UI creation)
        self.weight_slider = None
        self.weight_display = None
        self.status_display = None
        self.event_log = None
        
        # Initialize time service and storage
        self.app_start_time = None
        
        # Setup timers (but don't start them yet)
        self._setup_timers()
    
    def _setup_timers(self):
        """Setup all the application timers"""
        # Main drink reminder timer
        self.timer_manager.add_timer(
            'drink_reminder',
            self.reminder_timer_minutes,
            self._drink_reminder_callback,
            self.random_threshold_minutes
        )
        
        # Bad orientation timer
        self.timer_manager.add_timer(
            'bad_orientation',
            self.bad_orientation_interval,
            self._bad_orientation_callback
        )
        
        # Empty reminder timer
        self.timer_manager.add_timer(
            'empty_reminder',
            self.empty_reminder_interval,
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
    
    async def initialize_app(self):
        """Initialize the application with time sync and storage"""
        # Prevent multiple initializations
        if hasattr(self, '_app_initialized') and self._app_initialized:
            return
        
        try:
            # Sync time first (only if not recently synced)
            if not time_service.last_sync_time:
                print("🕐 Syncing time with API...")
                await time_service.sync_time()
            
            # Set app start time
            self.app_start_time = time_service.get_accurate_time()
            print(f"🚀 App started at: {self.app_start_time}")
            
            # Initialize hydration tracking
            self._check_daily_reset()
            print(f"💧 Hydration tracking initialized. Daily goal: {self.daily_goal_ml}ml, Current progress: {self.daily_consumed_ml}ml")
            print(f"🕐 Hydration window: {self.hydration_start_hour:02d}:00-{self.hydration_end_hour:02d}:00 ({self.hydration_end_hour - self.hydration_start_hour}h), Target rate: {self.reasonable_ml_per_hour}ml/h")
            
            # Check for unexpected shutdown from previous session
            self._check_unexpected_shutdown()
            
            # Setup signal handlers for graceful shutdown
            self._setup_signal_handlers()
            
            # Cleanup old logs
            storage.cleanup_old_logs(days=30)
            
            # Log app start event
            self.event_manager.trigger_event('app_started', {
                'start_time': self.app_start_time.isoformat(),
                'time_synced': time_service.last_sync_time is not None
            })
            
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
            
            # Save final state
            if self.app_start_time:
                storage.save_app_state(self.app_start_time, self.event_manager.event_counts)
            
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
        """Main drink reminder callback"""
        # Increase dehydration severity with each missed reminder
        self.dehydration_severity += 1
        
        # Get hydration window info for urgency context
        hydration_info = self._get_hydration_window_info()
        
        # Create more urgent reminder message if time is running out
        if hydration_info['urgency_factor'] > 2.0 and hydration_info['time_status'] == "in_window":
            reminder_message = f"💧 URGENT Drink Reminder! Only {hydration_info['hours_remaining']:.1f}h left! Need {hydration_info['remaining_ml_needed']:.0f}ml more! Dehydration Level: {self.dehydration_severity}"
        elif hydration_info['urgency_factor'] > 1.0 and hydration_info['time_status'] == "in_window":
            reminder_message = f"💧 Priority Drink Reminder! {hydration_info['hours_remaining']:.1f}h remaining. Need {hydration_info['remaining_ml_needed']:.0f}ml. Dehydration Level: {self.dehydration_severity}"
        elif hydration_info['time_status'] == "after_window":
            reminder_message = f"💧 Late Drink Reminder (after hydration hours). Dehydration Level: {self.dehydration_severity}"
        elif hydration_info['time_status'] == "before_window":
            reminder_message = f"💧 Early Drink Reminder (before hydration hours). Dehydration Level: {self.dehydration_severity}"
        else:
            reminder_message = f"💧 Drink Reminder! Dehydration Level: {self.dehydration_severity}"
        
        event_data = {
            'dehydration_severity': self.dehydration_severity,
            'hydration_window': hydration_info
        }
        
        event = self.event_manager.trigger_event('drink_reminder', 
                                                timer_name='drink_reminder',
                                                data=event_data)
        
        # Potentially adjust reminder frequency based on urgency
        if hydration_info['urgency_factor'] > 2.5 and hydration_info['time_status'] == "in_window":
            # High urgency - consider more frequent reminders
            print(f"⚡ High urgency detected! Consider more frequent reminders.")
            # Could implement dynamic timer adjustment here in the future
        
        # Queue UI updates for background tasks - with timeout protection
        try:
            await asyncio.wait_for(
                self.ui_update_queue.put(('toast', reminder_message, 'warning' if hydration_info['urgency_factor'] > 1.0 else 'info')), 
                timeout=5.0
            )
            await asyncio.wait_for(
                self.ui_update_queue.put(('update_log', None)), 
                timeout=5.0
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Continue operation even if UI updates fail
            print(f"DRINK REMINDER: {reminder_message}")
    
    def _calculate_hydration_improvement_factor(self, amount_consumed_ml: float) -> float:
        """Calculate hydration improvement factor based on amount consumed, dehydration severity, and time urgency"""
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
        
        # Determine message type and content based on improvement factor
        if improvement_factor >= 4.0:
            # Very high improvement - excellent timing/amount
            message = f"🌟 Outstanding! {amount_consumed_ml:.0f}ml at perfect timing! 💪{time_context}"
            message_type = "positive"
        elif improvement_factor >= 3.0:
            # High improvement - high praise
            message = f"🎉 Excellent! You drank {amount_consumed_ml:.0f}ml! Great hydration boost! 💪{time_context}"
            message_type = "positive"
        elif improvement_factor >= 2.0:
            # Good improvement - moderate praise  
            message = f"👍 Good job! You drank {amount_consumed_ml:.0f}ml. Keep up the good hydration! 💧{time_context}"
            message_type = "positive"
        elif improvement_factor >= 1.0:
            # Some improvement - encouragement
            message = f"✅ Nice! You drank {amount_consumed_ml:.0f}ml. Your body appreciates it! 🙂{time_context}"
            message_type = "info"
        elif improvement_factor >= 0.5:
            # Small improvement - gentle encouragement
            message = f"💧 You drank {amount_consumed_ml:.0f}ml. Every sip counts{time_context}"
            message_type = "info"
        else:
            # Very small improvement - more encouragement needed
            message = f"🚰 You drank {amount_consumed_ml:.0f}ml. Try for bigger sips{time_context}"
            message_type = "warning"
        
        # Add urgency context for high urgency situations
        if hydration_info['urgency_factor'] > 2.0 and hydration_info['time_status'] == "in_window":
            if hydration_info['remaining_ml_needed'] > 0:
                message += f" Need {hydration_info['remaining_ml_needed']:.0f}ml more!"
        
        return message, message_type
    
    async def _handle_drink_event(self, amount_consumed_ml: float):
        """Handle a drink event with hydration improvement factor calculation"""
        if amount_consumed_ml <= 0:
            return
        
        # Get hydration window info for context
        hydration_info = self._get_hydration_window_info()
        
        # Calculate hydration improvement factor (now includes time urgency)
        improvement_factor = self._calculate_hydration_improvement_factor(amount_consumed_ml)
        
        # Update daily consumption
        self.daily_consumed_ml += amount_consumed_ml
        
        # Reduce dehydration severity based on improvement factor
        severity_reduction = max(1, int(improvement_factor))
        self.dehydration_severity = max(0, self.dehydration_severity - severity_reduction)
        
        # Get appropriate message (now includes time context)
        message, message_type = self._get_hydration_message(amount_consumed_ml, improvement_factor)
        
        # Create drink event with rich data including hydration window info
        event_data = {
            'amount_ml': amount_consumed_ml,
            'improvement_factor': improvement_factor,
            'dehydration_severity_before': self.dehydration_severity + severity_reduction,
            'dehydration_severity_after': self.dehydration_severity,
            'daily_consumed_ml': self.daily_consumed_ml,
            'daily_goal_ml': self.daily_goal_ml,
            'daily_progress_percent': (self.daily_consumed_ml / self.daily_goal_ml) * 100,
            'hydration_window': hydration_info
        }
        
        # Trigger drink event
        event = self.event_manager.trigger_event('drink', data=event_data)
        
        # Reset drink reminder timer since they just drank
        self.timer_manager.reset_timer('drink_reminder')
        print(f"🔄 Drink reminder timer reset due to consumption of {amount_consumed_ml:.0f}ml")
        
        # Show hydration message
        await self._show_toast(f"{message} (Factor: {improvement_factor:.1f})", message_type)
        
        return event
    
    def _check_daily_reset(self):
        """Check if we need to reset daily consumption tracking"""
        current_date = time_service.get_accurate_time().date()
        if current_date != self.last_daily_reset:
            print(f"🌅 Daily reset: {self.daily_consumed_ml}ml consumed yesterday")
            self.daily_consumed_ml = 0
            self.last_daily_reset = current_date
            # Reset dehydration severity for new day
            self.dehydration_severity = 0
    
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
        current_time = time_service.get_accurate_time()
        current_hour = current_time.hour
        current_minute = current_time.minute
        
        # Calculate time until end of hydration window
        if self.hydration_start_hour <= self.hydration_end_hour:
            # Normal case: 7am-10pm
            if current_hour < self.hydration_start_hour:
                # Before window starts
                hours_until_start = self.hydration_start_hour - current_hour
                hours_in_window = self.hydration_end_hour - self.hydration_start_hour
                time_status = "before_window"
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
        """Bad orientation reminder callback"""
        if not self._is_bottle_vertical():
            event = self.event_manager.trigger_event('bad_orientation', timer_name='bad_orientation')
            try:
                await asyncio.wait_for(
                    self.ui_update_queue.put(('toast', f'⚠️ Bottle not vertical - readings may be inaccurate (#{event.severity})', 'warning')), 
                    timeout=5.0
                )
                await asyncio.wait_for(
                    self.ui_update_queue.put(('update_log', None)), 
                    timeout=5.0
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # Continue operation even if UI updates fail
                print(f"BAD ORIENTATION: Warning #{event.severity} triggered at {event.timestamp}")
    
    async def _empty_reminder_callback(self):
        """Empty bottle reminder callback"""
        if self.is_empty_state:
            event = self.event_manager.trigger_event('empty_reminder', timer_name='empty_reminder')
            try:
                await asyncio.wait_for(
                    self.ui_update_queue.put(('toast', f'🚨 Bottle still empty! Please refill (#{event.severity})', 'negative')), 
                    timeout=5.0
                )
                await asyncio.wait_for(
                    self.ui_update_queue.put(('update_log', None)), 
                    timeout=5.0
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # Continue operation even if UI updates fail
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
            try:
                await asyncio.wait_for(
                    self.ui_update_queue.put(('toast', f'🔧 Consider recalibrating the bottle weight (#{event.severity})', 'info')), 
                    timeout=5.0
                )
                await asyncio.wait_for(
                    self.ui_update_queue.put(('update_log', None)), 
                    timeout=5.0
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # Continue operation even if UI updates fail
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
        """Show a toast notification"""
        # Use NiceGUI notification system
        ui.notify(
            message, 
            type=type_, 
            position='top-right',
            timeout=5000,
            close_button=True
        )
    
    async def _process_ui_updates(self):
        """Process UI updates from background tasks"""
        while True:
            try:
                # Wait for UI update requests with a longer timeout
                update_type, message, *args = await asyncio.wait_for(
                    self.ui_update_queue.get(), timeout=10.0)
                
                # Schedule UI updates to run in the main event loop
                if update_type == 'toast':
                    try:
                        await asyncio.wait_for(
                            self._show_toast(message, args[0] if args else 'info'), 
                            timeout=3.0
                        )
                        # Also log to console for debugging
                        print(f"TOAST [{args[0] if args else 'INFO'}]: {message}")
                    except (RuntimeError, asyncio.TimeoutError, asyncio.CancelledError):
                        # If UI context is not available or cancelled, print to console
                        print(f"TOAST [{args[0] if args else 'INFO'}]: {message}")
                elif update_type == 'update_log':
                    try:
                        await asyncio.wait_for(
                            self._update_event_log(), 
                            timeout=3.0
                        )
                    except (RuntimeError, asyncio.TimeoutError, asyncio.CancelledError):
                        # If UI context is not available or cancelled, skip
                        pass
                elif update_type == 'update_displays':
                    try:
                        await asyncio.wait_for(
                            self._update_displays(), 
                            timeout=3.0
                        )
                    except (RuntimeError, asyncio.TimeoutError, asyncio.CancelledError):
                        # If UI context is not available or cancelled, skip
                        pass
                    
            except asyncio.TimeoutError:
                # Continue processing - this is normal when no UI updates are pending
                continue
            except asyncio.CancelledError:
                # Task was cancelled - exit gracefully
                print("UI update processor cancelled")
                break
            except Exception as e:
                print(f"Error processing UI update: {e}")
                # Continue processing other updates
                continue
    
    async def _update_displays(self):
        """Update all UI displays"""
        try:
            if self.weight_display:
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
                
                self.weight_display.text = f'Total: {self.current_weight}g | Drink: {drink_grams:.0f}g ({drink_percent:.1f}%) | Daily: {self.daily_consumed_ml:.0f}/{self.daily_goal_ml}ml ({daily_progress:.1f}%){time_status}{urgency_indicator}'
            
            if self.status_display:
                orientation_status = "✅ Vertical" if self._is_bottle_vertical() else "⚠️ Tilted"
                empty_status = "🚨 Empty" if self.is_empty_state else "💧 Has Drink"
                
                # Enhanced dehydration status with time context
                hydration_info = self._get_hydration_window_info()
                if self.dehydration_severity == 0:
                    if hydration_info['urgency_factor'] > 2.0:
                        dehydration_status = f"💧 Hydrated but URGENT timing!"
                    else:
                        dehydration_status = f"💧 Well Hydrated"
                else:
                    if hydration_info['urgency_factor'] > 2.0:
                        dehydration_status = f"🚨 Dehydration Level: {self.dehydration_severity} + URGENT!"
                    else:
                        dehydration_status = f"🚨 Dehydration Level: {self.dehydration_severity}"
                
                self.status_display.text = f'{orientation_status} | {empty_status} | {dehydration_status}'
        except Exception as e:
            print(f"Error updating displays: {e}")
    
    async def _update_event_log(self):
        """Update the event log display"""
        try:
            if self.event_log:
                # Show last 10 events
                recent_events = self.event_manager.events[-10:]
                log_text = ""
                for event in reversed(recent_events):
                    time_str = event.timestamp.strftime("%H:%M:%S")
                    if event.timer_name:
                        log_text += f"[{time_str}] {event.timer_name}:{event.event_type} (#{event.severity})\n"
                    else:
                        log_text += f"[{time_str}] {event.event_type} (#{event.severity})\n"
                self.event_log.value = log_text
            else:
                print("Warning: event_log not available yet")
        except RuntimeError:
            # If called from background task, skip UI update
            print("Warning: RuntimeError in _update_event_log - probably no UI context")
            pass
        except Exception as e:
            print(f"ERROR: Exception in _update_event_log: {e}")
            
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
            self.timer_manager.deactivate_timer('bad_orientation')
        
        self.previous_weight = self.current_weight
        await self._update_displays()
        await self._update_event_log()
    
    async def _handle_very_empty(self):
        """Handle very empty state with user confirmation"""
        result = await ui.run_javascript('''
            return confirm("Bottle appears to be completely empty. Recalibrate bottle weight?");
        ''')
        
        if result:
            # Recalibrate - set current weight as new bottle weight
            self.bottle_weight = self.current_weight
            self.is_empty_state = True
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
        await self._update_displays()
    
    async def on_submit_weight(self):
        """Callback for submit button"""
        print(f"Submit weight: Previous={self.previous_weight}g, Current={self.current_weight}g")
        await self._handle_weight_change()
    
    async def on_accelerometer_change(self, event=None):
        """Callback for accelerometer changes"""
        await self._update_displays()
        
        # Check orientation and activate/deactivate bad orientation timer based on current orientation
        if not self._is_bottle_vertical():
            self.timer_manager.activate_timer('bad_orientation')
        else:
            self.timer_manager.deactivate_timer('bad_orientation')
        
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
            
            timer_status.append({
                'name': name.replace('_', ' ').title(),
                'status': status,
                'interval': f"{timer.interval_minutes}m",
                'countdown': countdown,
                'next_trigger': timer.next_trigger_time.strftime('%H:%M:%S') if timer.next_trigger_time else "N/A"
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
                        row['next_trigger'].text = status['next_trigger']
            else:
                print("Warning: timer_rows not available yet")
        except Exception as e:
            print(f"Error updating timer panel: {e}")
            
    def create_ui(self):
        """Create the main UI"""
        ui.page_title('Drink Reminder Simulator')
        
        with ui.card().classes('w-full max-w-6xl mx-auto p-6'):
            ui.label('🍺 Drink Reminder Simulator').classes('text-3xl font-bold text-center mb-6')
            
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
                        
                        self.weight_display = ui.label(f'Total: {self.current_weight}g | Drink: 0g (0.0%)').classes('text-lg font-mono')
                    
                    # Accelerometer Controls  
                    with ui.card().classes('mb-4 p-4'):
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
                
                # Right Column - Status and Events
                with ui.column().classes('flex-1 min-w-0'):
                    # Status Display
                    with ui.card().classes('mb-4 p-4'):
                        ui.label('📊 Status').classes('text-xl font-semibold mb-4')
                        self.status_display = ui.label('✅ Vertical | 💧 Has Drink').classes('text-lg')
                    
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
                                next_label = ui.label('').classes('w-16 font-mono text-xs')
                                
                                self.timer_rows.append({
                                    'name': name_label,
                                    'status': status_label,
                                    'interval': interval_label,
                                    'countdown': countdown_label,
                                    'next_trigger': next_label
                                })
                    
                    # Event Log
                    with ui.card().classes('p-4'):
                        ui.label('📋 Event Log').classes('text-xl font-semibold mb-4')
                        self.event_log = ui.textarea(value='').classes('w-full mb-4').props('readonly rows=8')
                        
                        with ui.row().classes('gap-2 w-full'):
                            async def clear_events():
                                self.event_manager.clear_events()
                                await self._update_event_log()
                            
                            ui.button('Clear Events', on_click=clear_events).classes('bg-red-500 flex-1')
                            
                            async def test_drink_reminder():
                                await self._drink_reminder_callback()
                                # Force immediate UI updates  
                                await self._update_event_log()
                                await self._update_timer_panel()
                            
                            ui.button('Test Drink Reminder', on_click=test_drink_reminder).classes('bg-blue-500 flex-1')
        
        print("Info: UI elements created, starting background tasks")
        
        # Initialize displays and start UI update processor
        asyncio.create_task(self._update_displays())
        asyncio.create_task(self._update_event_log())
        asyncio.create_task(self._process_ui_updates())
        
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
        
        # Create the auto-refresh timer in the main UI context (every 2 seconds for real-time updates)
        ui.timer(2.0, callback=lambda: asyncio.create_task(self._update_timer_panel()))

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
        # Save final state
        if drink_app.app_start_time:
            storage.save_app_state(drink_app.app_start_time, drink_app.event_manager.event_counts)
        
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