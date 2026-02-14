# Taskmaster

Taskmaster is a powerful and flexible process management system designed to control and monitor background tasks, services, and applications. It provides a robust framework for managing the lifecycle of multiple processes, ensuring they run reliably and efficiently. This project is inspired by `supervisord`, offering a similar feature set with a simplified, YAML-based configuration.

## Key Features

- **Process Management**: Start, stop, restart, and monitor multiple processes from a single command-line interface.
- **Configuration via YAML**: Define program behaviors, environment variables, and logging options in an easy-to-read `config.yaml` file.
- **Automatic Restart**: Configure programs to restart automatically on exit, with customizable policies (always, never, or on unexpected exit codes).
- **Web Dashboard**: A built-in web interface provides a real-time overview of all managed processes, including their status, uptime, and PID.
- **Detailed Logging**: Each program's `stdout` and `stderr` streams are captured in separate log files for easy debugging.
- **Graceful Shutdown**: Ensures that processes are terminated gracefully, with configurable stop signals and timeouts.
- **Multi-threading for Monitoring**: A dedicated thread monitors the health of all child processes, handling restarts and logging without blocking the main application.

## Project Structure

The project is organized into several key components:

- **`main.py`**: The core of the application, responsible for parsing the configuration, managing processes, and handling user commands.
- **`config.yaml`**: The main configuration file where all programs and their behaviors are defined.
- **`logger.py`**: A custom logging module that provides file-based logging with rotation.
- **`web_dashboard.py`**: Implements the web-based dashboard for real-time process monitoring.
- **`config_validator.py`**: Ensures that the `config.yaml` file is well-formed and contains valid settings.
- **`scripts/`**: A directory containing example shell scripts that can be managed by Taskmaster.
- **`logs/`**: The default directory where all process logs are stored.
- **`main.cpp`**: An example of a C++ application that can be managed by Taskmaster.

## Why Use Threads?

In this project, we use a multi-threaded approach for a specific reason: **non-blocking monitoring**.

- **`ProcessMonitor` Thread**: A dedicated thread, `ProcessMonitor`, runs in the background to continuously check the status of all child processes. This is crucial for a process manager, as it allows the main application to remain responsive to user commands while simultaneously keeping an eye on the health of the managed tasks.

- **Why Not Processes?**: While we could have used a separate process for monitoring, a thread is a more lightweight and efficient solution for this particular task. Since the monitor's job is to share and manage data related to other processes (which are already isolated), a thread is a natural fit. It can directly access the `JobManager`'s data structures (with proper locking) without the overhead of inter-process communication (IPC).

In summary, we create **processes** for the tasks we want to manage (e.g., `logger.sh`, `worker.sh`) because they need to run in isolation. We use a **thread** to monitor these processes because it's an efficient way to handle a background task that needs to share data with the main application.

## How to Create a Process

To add a new program to Taskmaster, you simply need to add a new entry in the `config.yaml` file. Here's a breakdown of the configuration options:

```yaml
programs:
  my_program:
    cmd: "/path/to/your/script.sh"  # The command to execute
    numprocs: 1                      # Number of instances to run
    autostart: true                  # Start automatically when Taskmaster starts
    autorestart: "unexpected"        # Restart if it exits with an unexpected code
    exitcodes: [0]                   # Expected exit codes (for autorestart)
    startretries: 3                  # Number of times to retry starting
    stopsignal: "TERM"               # Signal to use for stopping the process
    stdout: "/path/to/stdout.log"    # Path to the stdout log file
    stderr: "/path/to/stderr.log"    # Path to the stderr log file
    env:                             # Environment variables
      MY_VAR: "my_value"

## Configuration File Explained (`config.yaml`)

The configuration file is the heart of Taskmaster. It defines all programs and how they should run. The root key is `programs`, and each program has its own configuration block.

### Global Structure

```yaml
programs:
    program_name:
        # program options...
```

### Per-Program Fields

- **`cmd`**: The exact command Taskmaster will execute. This can be a script (bash, python, etc.) or a binary. It is executed using `subprocess.Popen`.
- **`numprocs`**: How many instances of this program to run. Taskmaster will start multiple processes and track them as `name:0`, `name:1`, etc.
- **`workingdir`**: The working directory for the process. This is where the program will execute (like a `cd` before running).
- **`umask`**: The file permission mask for the process. This controls default permissions of files created by that program.
- **`autostart`**: If `true`, the program starts automatically when Taskmaster boots.
- **`autorestart`**: Restart policy when a process exits:
    - `always`: restart no matter what exit code.
    - `unexpected`: restart only if the exit code is not in `exitcodes`.
    - `never`: never restart.
- **`exitcodes`**: A list of exit codes considered "normal". Used with `autorestart: unexpected`.
- **`startretries`**: How many times Taskmaster will retry starting a program if it fails during the startup window.
- **`starttime`**: The number of seconds a process must stay alive to be considered "successfully started".
- **`stopsignal`**: The signal used to stop the process (e.g., `TERM`, `INT`).
- **`stoptime`**: How long Taskmaster waits before force-killing the process if it doesn't stop.
- **`stdout`** / **`stderr`**: File paths where the program’s standard output and error streams are written.
- **`env`**: A dictionary of environment variables injected into the process at launch.

### Signals Explained

Taskmaster uses POSIX signals to stop programs cleanly. The `stopsignal` field determines which signal is sent first. If the process doesn’t exit within `stoptime`, Taskmaster sends `SIGKILL` to force termination.

Common signals used in this project:

- **`SIGTERM`** (`TERM`): The default, polite termination request. Well-behaved processes should catch this and exit cleanly.
- **`SIGINT`** (`INT`): Similar to pressing Ctrl+C in a terminal. Useful for scripts that are written to handle interrupts.
- **`SIGKILL`** (`KILL`): Immediate termination, cannot be caught or ignored. Taskmaster only uses this as a last resort after `stoptime` expires.

### Example From This Project

```yaml
programs:
    worker:
        cmd: "/bin/bash /home/kamui/Desktop/taskmaster/scripts/worker.sh"
        numprocs: 3
        workingdir: /home/kamui/Desktop/taskmaster
        autostart: true
        autorestart: never
        exitcodes: [0, 2, 3, 4, 1]
        startretries: 3
        starttime: 3
        stopsignal: INT
        stoptime: 5
        stdout: /home/kamui/Desktop/taskmaster/logs/worker.stdout
        stderr: /home/kamui/Desktop/taskmaster/logs/worker.stderr
        env:
            WORKER_ID: "1"
            ENVIRONMENT: "production"
```
```

## Usage

1. **Configure `config.yaml`**: Define the programs you want to manage.
2. **Run Taskmaster**:
   ```bash
   python3 main.py
   ```
3. **Use the Command-Line Interface**:
   - `status`: View the status of all programs.
   - `start <program_name>`: Start a specific program.
   - `stop <program_name>`: Stop a program.
   - `restart <program_name>`: Restart a program.
   - `exit`: Stop all programs and exit Taskmaster.

4. **Access the Web Dashboard**:
   - Open your web browser and navigate to `http://localhost:8080` to see the real-time dashboard.

This project serves as a comprehensive example of how to build a robust process management system, combining the power of Python's multi-threading capabilities with clear, declarative configuration.

## How It Works: In-Depth

### The Logging System

The logging in Taskmaster is split into two main parts: logging for the Taskmaster application itself, and logging for the processes it manages.

1.  **Taskmaster Application Logging (`logger.py`)**:
    - The `TaskmasterLogger` class in `logger.py` is responsible for logging the internal events of the Taskmaster application (e.g., "Starting process 'worker'", "Process 'logger' exited unexpectedly").
    - It uses Python's standard `logging` module and is configured with a `RotatingFileHandler`. This is important because it prevents the main log file (`taskmaster.log`) from growing indefinitely. When the log file reaches a certain size, it is automatically rotated, and older logs are kept in backup files.
    - This logger provides methods like `info()`, `warning()`, and `error()` that are used throughout `main.py` to record what the application is doing.

2.  **Managed Process Logging (`config.yaml`)**:
    - The `stdout` and `stderr` output of each individual program (like `worker.sh` or `ping_monitor.sh`) is not handled by `logger.py`.
    - Instead, when Taskmaster starts a process using `subprocess.Popen` in `main.py`, it redirects the process's standard output and standard error streams to the files specified in the `stdout` and `stderr` fields of your `config.yaml`.
    - This design decision keeps the logs for each managed program separate and clean, making it much easier to debug a specific program without having to sift through the main application's logs.

### The Web Dashboard

The web dashboard provides a real-time, read-only view of the status of all managed processes.

1.  **How It's Started**:
    - The web dashboard is initialized and started within the `JobManager` class in `main.py`.
    - When `JobManager` is created, it creates an instance of the `WebDashboard` class from `web_dashboard.py`.
    - The `WebDashboard`'s `start()` method is then called, which launches Python's built-in `HTTPServer` in a **new daemon thread**.
    - Running the server in a separate thread is critical. It allows the web dashboard to run in the background and handle HTTP requests without blocking the main application thread, which needs to remain free to accept user commands from the command-line interface.

2.  **How It Works**:
    - The `DashboardHandler` class inside `web_dashboard.py` is responsible for handling all incoming HTTP requests.
    - When you access the dashboard in your browser, the handler serves a static HTML page.
    - This HTML page contains JavaScript that periodically sends requests to the `/api/status` endpoint.
    - The `serve_status_json()` method in the handler responds to these API requests by collecting the current status of all jobs from the `JobManager` and sending it back as a JSON object.
    - The JavaScript on the page then parses this JSON and dynamically updates the status table in the HTML, giving you a real-time view of your processes without ever needing to refresh the page.

