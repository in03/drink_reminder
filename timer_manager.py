import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, Callable, Optional
from dataclasses import dataclass
from time_service import time_service
from persistent_storage import storage, TimerState

@dataclass
class Timer:
    name: str
    interval_minutes: int
    callback: Callable
    last_triggered: Optional[datetime] = None
    is_active: bool = True
    random_variance_minutes: int = 0
    next_trigger_time: Optional[datetime] = None

class TimerManager:
    def __init__(self, min_gap_minutes: int = 1):
        self.timers: Dict[str, Timer] = {}
        self.min_gap_minutes = min_gap_minutes
        self.last_any_timer = None
        self._running = False
        self._task = None
        self._save_task = None
    
    def add_timer(self, name: str, interval_minutes: int, callback: Callable, 
                  random_variance_minutes: int = 0):
        """Add a new timer"""
        # Check if we have saved state for this timer
        saved_states = storage.load_timer_states()
        saved_state = saved_states.get(name)
        
        current_time = time_service.get_accurate_time()
        
        # Create timer
        timer = Timer(
            name=name,
            interval_minutes=interval_minutes,
            callback=callback,
            random_variance_minutes=random_variance_minutes
        )
        
        # Restore state if available and valid
        if saved_state:
            try:
                if saved_state.last_triggered:
                    timer.last_triggered = datetime.fromisoformat(saved_state.last_triggered)
                timer.is_active = saved_state.is_active
                
                # Calculate next trigger time if we don't have one
                if saved_state.next_trigger_time:
                    timer.next_trigger_time = datetime.fromisoformat(saved_state.next_trigger_time)
                else:
                    timer.next_trigger_time = self._calculate_next_trigger(timer, current_time)
            except Exception as e:
                print(f"Error restoring timer state for {name}: {e}")
                # Set next trigger time for new timer (start from current time + interval)
                timer.next_trigger_time = self._calculate_next_trigger(timer, current_time)
        else:
            # New timer - set next trigger time to start from now
            timer.next_trigger_time = self._calculate_next_trigger(timer, current_time)
        
        self.timers[name] = timer
        print(f"Timer '{name}' added. Next trigger: {timer.next_trigger_time}")
        
        # Save state immediately
        self._save_timer_states()
    
    def remove_timer(self, name: str):
        """Remove a timer"""
        if name in self.timers:
            del self.timers[name]
    
    def activate_timer(self, name: str):
        """Activate a timer"""
        if name in self.timers:
            self.timers[name].is_active = True
    
    def deactivate_timer(self, name: str):
        """Deactivate a timer"""
        if name in self.timers:
            self.timers[name].is_active = False
    
    def reset_timer(self, name: str):
        """Reset a timer's last triggered time"""
        if name in self.timers:
            current_time = time_service.get_accurate_time()
            self.timers[name].last_triggered = None
            self.timers[name].next_trigger_time = self._calculate_next_trigger(self.timers[name], current_time)
            self._save_timer_states()
    
    def _calculate_next_trigger(self, timer: Timer, current_time: datetime) -> datetime:
        """Calculate when a timer should next trigger"""
        base_interval = timer.interval_minutes
        
        # Apply random variance
        if timer.random_variance_minutes > 0:
            variance = random.randint(-timer.random_variance_minutes, timer.random_variance_minutes)
            interval = max(1, base_interval + variance)  # Ensure minimum 1 minute
        else:
            interval = base_interval
        
        return current_time + timedelta(minutes=interval)
    
    def _should_trigger_timer(self, timer: Timer) -> bool:
        """Check if a timer should be triggered"""
        if not timer.is_active or not timer.next_trigger_time:
            return False
        
        now = time_service.get_accurate_time()
        
        # Check if enough time has passed since any timer fired
        if (self.last_any_timer and 
            (now - self.last_any_timer).total_seconds() < self.min_gap_minutes * 60):
            return False
        
        # Check if it's time to trigger
        return now >= timer.next_trigger_time
    
    async def _timer_loop(self):
        """Main timer loop"""
        while self._running:
            for timer in self.timers.values():
                if self._should_trigger_timer(timer):
                    # Trigger the timer
                    try:
                        current_time = time_service.get_accurate_time()
                        
                        # Use timeout to prevent hanging on client disconnections
                        await asyncio.wait_for(timer.callback(), timeout=30.0)
                        
                        timer.last_triggered = current_time
                        self.last_any_timer = current_time
                        
                        # Calculate next trigger time
                        timer.next_trigger_time = self._calculate_next_trigger(timer, current_time)
                        
                        print(f"Timer '{timer.name}' triggered. Next trigger: {timer.next_trigger_time}")
                        
                        # Save state after triggering
                        self._save_timer_states()
                    except asyncio.TimeoutError:
                        print(f"Timer '{timer.name}' callback timed out (likely due to client disconnection)")
                        # Still update the timer state to prevent immediate re-triggering
                        current_time = time_service.get_accurate_time()
                        timer.last_triggered = current_time
                        self.last_any_timer = current_time
                        timer.next_trigger_time = self._calculate_next_trigger(timer, current_time)
                        self._save_timer_states()
                    except asyncio.CancelledError:
                        print(f"Timer '{timer.name}' callback was cancelled (client disconnected)")
                        # Still update the timer state to prevent immediate re-triggering
                        current_time = time_service.get_accurate_time()
                        timer.last_triggered = current_time
                        self.last_any_timer = current_time
                        timer.next_trigger_time = self._calculate_next_trigger(timer, current_time)
                        self._save_timer_states()
                    except Exception as e:
                        print(f"Error in timer {timer.name}: {e}")
                        # Don't update timer state on unexpected errors to allow retry
            
            # Check every 60 seconds
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                # Timer loop was cancelled - exit gracefully
                print("Timer loop cancelled")
                break 
    
    async def start(self):
        """Start the timer manager"""
        if not self._running:
            # Ensure time is synced before starting (but don't block on failures)
            # Commented out - app initialization already handles time sync
            # try:
            #     await time_service.ensure_time_sync()
            # except Exception as e:
            #     print(f"⚠️  Time sync failed during timer start: {e}")
            
            self._running = True
            self._task = asyncio.create_task(self._timer_loop())
            
            # Start periodic save task
            self._save_task = asyncio.create_task(self._periodic_save())
            
            print("⏰ Timer manager started successfully")
    
    async def stop(self):
        """Stop the timer manager and cleanup resources"""
        print("Timer loop cancelled")
        self._running = False
        
        # Save final state
        self._save_timer_states()
        
        # Cancel and cleanup tasks properly
        tasks_to_cleanup = []
        for task in [self._task, self._save_task]:
            if task and not task.done():
                tasks_to_cleanup.append(task)
                task.cancel()
        
        # Wait for all tasks to complete cancellation
        if tasks_to_cleanup:
            try:
                await asyncio.wait(tasks_to_cleanup, timeout=2.0)
            except asyncio.TimeoutError:
                print("Warning: Some timer tasks didn't cancel within timeout")
            
        # Clear task references
        self._task = None
        self._save_task = None
    
    def _save_timer_states(self):
        """Save current timer states to storage"""
        try:
            timer_states = {}
            for name, timer in self.timers.items():
                timer_states[name] = TimerState(
                    name=timer.name,
                    last_triggered=timer.last_triggered.isoformat() if timer.last_triggered else None,
                    interval_minutes=timer.interval_minutes,
                    random_variance_minutes=timer.random_variance_minutes,
                    is_active=timer.is_active,
                    next_trigger_time=timer.next_trigger_time.isoformat() if timer.next_trigger_time else None
                )
            storage.save_timer_states(timer_states)
        except Exception as e:
            print(f"Error saving timer states: {e}")
    
    async def _periodic_save(self):
        """Periodically save timer states"""
        while self._running:
            try:
                await asyncio.sleep(600)  # Save every 10 minutes
                self._save_timer_states()
                # No need for periodic time sync since all activity is relative
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Error in periodic save: {e}") 