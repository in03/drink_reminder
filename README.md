# 🍺 Drink Reminder Simulator

A comprehensive Python application that simulates a smart drink bottle monitoring system using NiceGUI. This simulator mocks hardware sensors and provides a complete testing environment before implementing the actual hardware solution.

## Features

### Core Functionality
- **Weight Monitoring**: Simulates a load cell with weight slider (710g - 1810g range)
- **Accelerometer Simulation**: 3-axis orientation control with graphical sliders
- **Smart Event Detection**: Multiple event types with severity tracking
- **Configurable Timers**: Multiple timer systems with collision avoidance
- **Modern UI**: Clean, responsive interface built with NiceGUI

### Event Types
- **empty**: Triggered when drink level reaches within 50g of minimum
- **very_empty**: Triggered at 10g threshold with recalibration option
- **filled_up**: Triggered when bottle reaches 90% capacity
- **partial_fill**: Triggered on moderate weight increases
- **drink_correction**: Triggered on small weight adjustments (+10g)
- **drink_reminder**: Configurable periodic reminders (45min ± 5min default)
- **bad_orientation**: Triggered when bottle isn't vertical (>10° tilt)
- **empty_reminder**: Continues until bottle is refilled
- **recalibrate_reminder**: Triggered if no very_empty event in 2 days

### Smart Features
- **Event Severity Tracking**: Each event type counts occurrences for escalating severity
- **Timer Collision Avoidance**: Minimum 1-minute gap between timer events
- **Automatic Tare Calibration**: Recalibrates bottle weight when very empty
- **Orientation Monitoring**: Warns when readings may be inaccurate due to tilt
- **Configurable Thresholds**: All parameters adjustable via environment variables

## Setup

### 1. Install Dependencies
```bash
uv sync
```

### 2. Configuration
Copy `sample-dotenv` to `.env` and adjust settings as needed:
```bash
cp sample-dotenv .env
```

Key configuration options:
- `REMINDER_TIMER_MINUTES`: Base reminder interval (default: 45)
- `RANDOM_THRESHOLD_MINUTES`: Random variance for reminder (default: 5)
- `MIN_WEIGHT/MAX_WEIGHT`: Bottle weight range (default: 710-1810g)
- `EMPTY_THRESHOLD`: Empty detection threshold (default: 50g)
- `ORIENTATION_THRESHOLD`: Maximum tilt angle (default: 10°)

### 3. Run the Application
```bash
python app.py
```

The application will start on `http://localhost:8080`

## Usage

### Weight Control
1. Use the weight slider to simulate drink consumption or refilling
2. Click "Submit Weight Change" to register the new weight and trigger events
3. Monitor the drink level display showing total weight, drink amount, and percentage

### Accelerometer Control
- **X-Axis**: Side-to-side tilt
- **Y-Axis**: Forward-backward tilt  
- **Z-Axis**: Up-down orientation (1.0 = perfectly vertical)

Tilt the bottle beyond 10° from vertical to trigger orientation warnings.

### Event Monitoring
- All events appear in the Event Log with timestamps and severity levels
- Toast notifications provide real-time feedback
- Severity increases with each occurrence of the same event type

### Testing Features
- **Clear Events**: Reset all event history and counters
- **Test Drink Reminder**: Manually trigger a reminder event
- **Recalibration**: Triggered automatically when very empty, or manually via confirmation dialog

## Architecture

### Modular Design
- `app.py`: Main application and UI
- `event_manager.py`: Event tracking and severity management
- `timer_manager.py`: Timer coordination and collision avoidance
- `sample-dotenv`: Environment configuration

### Timer System
- **Non-blocking**: All timers run asynchronously
- **Collision Avoidance**: Automatic spacing between timer events
- **Dynamic Activation**: Timers activate/deactivate based on conditions
- **Random Variance**: Prevents predictable timing patterns

### Event System
- **Severity Tracking**: Automatic escalation based on frequency
- **Data Logging**: Complete event history with timestamps
- **Type Classification**: Organized by event category for analysis

## Development Notes

### Design Principles
- **Simple & Idiomatic**: Clean Python code for easy porting to MicroPython/C++
- **Configurable**: Environment-based configuration for easy testing
- **Modular**: Separated concerns for maintainability
- **Async-Ready**: Built for non-blocking operations

### Future Hardware Implementation
This simulator provides the complete logic and timing that can be directly ported to:
- **MicroPython**: For microcontroller implementation
- **C++**: For embedded systems
- **Real Sensors**: Load cells, accelerometers, and timers

### Customization
Easily modify thresholds, add new event types, or adjust timer behavior by:
1. Updating the `.env` configuration
2. Adding new event types in `event_manager.py`
3. Creating additional timers in `timer_manager.py`
4. Extending the UI in `app.py`

## License

This project is designed for prototyping and testing smart bottle hardware systems. 