# Taskmaster Example Configuration

## Configuration (config.yaml)

| Program | Description | Autostart |
|---------|-------------|-----------|
| `logger` | Logs timestamps at regular intervals | ✅ Yes |
| `webserver` | Python HTTP server on port 8080 | ❌ No |
| `worker` | Simulates background task processing | ✅ Yes |
| `pingmonitor` | Monitors network connectivity | ❌ No |
| `counter` | Counts to 10 and exits (short-lived) | ❌ No |
| `sleeper` | Simple long-running sleep process | ❌ No |

## Scripts Created (scripts)

- **`logger.sh`** - Heartbeat logger with configurable interval
- **`worker.sh`** - Simulates task processing with random delays
- **`ping_monitor.sh`** - Pings a target and logs connectivity
- **`counter.sh`** - Counts to a number and exits

## Usage with Taskmaster

```
taskmaster> status           # See all programs status
taskmaster> start logger     # Start a specific program
taskmaster> stop worker      # Stop a program
taskmaster> restart sleeper  # Restart a program
taskmaster> exit             # Stop the main program
```



notes:
if autorestart: always -> always restart (regardless of exit code).
if autorestart: unexpected -> restart only when the process exit code is NOT in exitcodes.
if autorestart: never (or omitted) -> do not restart.
if a process dies before being marked successfully_started it is treated as a start failure and will be retried (subject to startretries).
Restarts stop after startretries attempts (the manager removes the instance and logs failure).