from pathlib import Path
import yaml
import os
import sys
import subprocess
import cmd
import threading
import time
import signal
from threading import Lock

# Minimal .env loader: simple KEY=VALUE parsing, ignores comments and blank lines.
def _simple_load_dotenv(path=None):
    try:
        env_path = Path(path) if path else Path(__file__).parent / '.env'
        if not env_path.exists():
            return
        with env_path.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                # Don't overwrite existing environment variables
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        # keep loader intentionally simple and failure-tolerant
        pass

# Try loading .env from project root (non-intrusive)
_simple_load_dotenv()

# Import bonus features (optional)
try:
    from logger import get_logger
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False

try:
    from web_dashboard import WebDashboard
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False

try:
    from config_validator import ConfigValidator
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False


class ProcessInfo:
    """Wrapper to store process and metadata"""
    def __init__(self, process, start_time, retry_count=0):
        self.process = process
        self.start_time = start_time
        self.retry_count = retry_count
        self.successfully_started = False


class ProcessMonitor(threading.Thread):
    """Thread that monitors the status of all jobs"""
    def __init__(self, job_manager, interval=1):
        super().__init__(daemon=True)
        self.job_manager = job_manager
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            self.check_jobs()
            time.sleep(self.interval)

    def stop(self):
        self.stop_event.set()

    def check_jobs(self):
        with self.job_manager.lock:  
            for name, proc_infos in list(self.job_manager.jobs.items()):
                program_cfg = self.job_manager.config.get(name)
                if not program_cfg:
                    continue
                
                autorestart = program_cfg.get('autorestart', 'never')
                exitcodes = program_cfg.get('exitcodes', [0])
                if isinstance(exitcodes, int):
                    exitcodes = [exitcodes]
                
                starttime = program_cfg.get('starttime', 1)
                startretries = program_cfg.get('startretries', 3)
                
                for i, proc_info in enumerate(proc_infos[:]):
                    # Check if process successfully started
                    if not proc_info.successfully_started:
                        elapsed = time.time() - proc_info.start_time
                        if elapsed >= starttime and proc_info.process.poll() is None:
                            proc_info.successfully_started = True
                            # Only log to file, not terminal
                            if self.job_manager.logger:
                                self.job_manager.logger.info(f"Program '{name}:{i}' successfully started")
                    
                    # Check if process exited
                    if proc_info.process.poll() is not None:
                        returncode = proc_info.process.returncode
                        
                        # Check if it died before being successfully started
                        if not proc_info.successfully_started:
                            if self.job_manager.logger:
                                self.job_manager.logger.warning(f"Program '{name}:{i}' died before startup (exit code {returncode})")
                            should_retry = True
                        else:
                            if self.job_manager.logger:
                                self.job_manager.logger.info(f"Program '{name}:{i}' exited with code {returncode}")
                            
                            # Determine if should restart based on autorestart policy
                            should_retry = False
                            if autorestart == "always":
                                should_retry = True
                            elif autorestart == "unexpected":
                                if returncode not in exitcodes:
                                    if self.job_manager.logger:
                                        self.job_manager.logger.warning(f"Exit code {returncode} unexpected (expected: {exitcodes})")
                                    should_retry = True
                        
                        # Handle restart logic
                        if should_retry:
                            if proc_info.retry_count < startretries:
                                proc_info.retry_count += 1
                                if self.job_manager.logger:
                                    self.job_manager.logger.info(f"Restarting '{name}:{i}' (attempt {proc_info.retry_count}/{startretries})")
                                time.sleep(1)
                                
                                # Start new process
                                new_proc_info = self.job_manager._start_single_process(name, program_cfg)
                                if new_proc_info:
                                    new_proc_info.retry_count = proc_info.retry_count
                                    proc_infos[i] = new_proc_info
                            else:
                                if self.job_manager.logger:
                                    self.job_manager.logger.error(f"Program '{name}:{i}' failed after {startretries} attempts")
                                proc_infos.remove(proc_info)
                        else:
                            proc_infos.remove(proc_info)
                
                # Clean up if no processes left
                if not proc_infos:
                    del self.job_manager.jobs[name]


class ShellCommand(cmd.Cmd):
    intro = "Welcome to Taskmaster. Type 'help' for available commands.\n"
    prompt = "taskmaster> "

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def do_status(self, arg):
        """Get status of programs: status [name]"""
        if not arg:
            self.manager.status_all_jobs()
        else:
            self.manager.status_jobs(arg)

    def do_start(self, arg):
        """Start a program: start <name>"""
        if not arg:
            print("Usage: start <program_name>")
            return
        self.manager.start_job(arg)

    def do_stop(self, arg):
        """Stop a program: stop <name>"""
        if not arg:
            print("Usage: stop <program_name>")
            return
        self.manager.stop_job(arg)

    def do_restart(self, arg):
        """Restart a program: restart <name>"""
        if not arg:
            print("Usage: restart <program_name>")
            return
        self.manager.restart_job(arg)

    def do_reload(self, arg):
        """Reload configuration file"""
        print("\n" + "="*60)
        print("Reloading Configuration")
        print("="*60)
        self.manager.reload_config()
        print("="*60 + "\n")

    def do_validate(self, arg):
        """Validate current configuration"""
        if VALIDATOR_AVAILABLE:
            ConfigValidator.print_validation_report(self.manager.config)
        else:
            print("Config validator not available")
    
    def do_summary(self, arg):
        """Show configuration summary"""
        if VALIDATOR_AVAILABLE:
            ConfigValidator.print_config_summary(self.manager.config)
        else:
            print(f"Total programs: {len(self.manager.config)}")

    def do_exit(self, arg):
        """Exit taskmaster"""
        print("Shutting down...")
        self.manager.stop_all_jobs()
        if self.manager.dashboard:
            self.manager.dashboard.stop()
        print("Goodbye!")
        return True

    def do_quit(self, arg):
        """Quit taskmaster (alias for exit)"""
        return self.do_exit(arg)


def load_config(file_path):
    """Parse YAML configuration file"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file {file_path} not found")
    
    with open(file_path, 'r') as f:
        try:
            config_data = yaml.load(f, Loader=yaml.FullLoader)
            return config_data.get('programs', {})
        except yaml.YAMLError as e:
            print(f"Error parsing YAML: {e}")
            sys.exit(1)


class JobManager:
    def __init__(self, config, config_path=None):
        self.lock = Lock()
        self.config = config
        self.config_path = config_path
        self.jobs = {}
        
        
        # Build email config from environment variables (optional)
        # Supported env vars: EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_USERNAME,
        # EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO (comma-separated)
        smtp_server = os.getenv('EMAIL_SMTP_SERVER') or os.getenv('SMTP_SERVER')
        if smtp_server:
            try:
                smtp_port = int(os.getenv('EMAIL_SMTP_PORT') or os.getenv('SMTP_PORT') or 587)
            except ValueError:
                smtp_port = 587

            username = os.getenv('EMAIL_USERNAME') or os.getenv('SMTP_USER')
            password = os.getenv('EMAIL_PASSWORD') or os.getenv('SMTP_PASS')
            from_addr = os.getenv('EMAIL_FROM') or username
            to_addrs_raw = os.getenv('EMAIL_TO') or os.getenv('EMAIL_TO_ADDRS') or ''
            to_addrs = [a.strip() for a in to_addrs_raw.split(',') if a.strip()]

            email_config = {
                'smtp_server': smtp_server,
                'smtp_port': smtp_port,
                'username': username,
                'password': password,
                'from_addr': from_addr,
                'to_addrs': to_addrs,
            }
        else:
            email_config = None

        # Initialize logger with optional email config
        self.logger = get_logger(email_config=email_config) if LOGGER_AVAILABLE else None
        
        # Start web dashboard
        self.dashboard = None
        if DASHBOARD_AVAILABLE:
            self.dashboard = WebDashboard(self, port=8080)
            self.dashboard.start()
        
        self.auto_start_jobs()
    
    def log(self, message, level='info'):
        """Log message - only to file, never to console"""
        if self.logger:
            if level == 'error':
                self.logger.error(message)
            elif level == 'warning':
                self.logger.warning(message)
            else:
                self.logger.info(message)
        # If no logger available, write to a simple log file
        else:
            try:
                with open('taskmaster.log', 'a') as f:
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                    f.write(f"{timestamp} - {level.upper()} - {message}\n")
            except:
                pass  # Silently fail if can't write

    def auto_start_jobs(self):
        """Start all programs with autostart enabled"""
        for name, program_cfg in self.config.items():
            if program_cfg.get('autostart', False):
                self.start_job(name)

    def status_jobs(self, name):
        """Show status of specific program"""
        proc_infos = self.jobs.get(name)
        # Use consistent column widths for nicer alignment
        col_instance = 20
        col_state = 12
        col_pid = 8
        col_uptime = 10
        col_retries = 8

        # If program exists in config but has no running instances, show STOPPED
        if not proc_infos:
            if name in self.config:
                print(f"\n{'Instance':<{col_instance}} {'State':<{col_state}} {'PID':<{col_pid}} {'Uptime':<{col_uptime}} {'Retries':<{col_retries}}")
                print("-" * (col_instance + col_state + col_pid + col_uptime + col_retries + 4))
                print(f"{name:<{col_instance}} {'STOPPED':<{col_state}} {'-':<{col_pid}} {'-':<{col_uptime}} {'-':<{col_retries}}")
                return
            else:
                print(f"No processes found for program '{name}'")
                return

        print(f"\n{'Instance':<{col_instance}} {'State':<{col_state}} {'PID':<{col_pid}} {'Uptime':<{col_uptime}} {'Retries':<{col_retries}}")
        print("-" * (col_instance + col_state + col_pid + col_uptime + col_retries + 4))

        for i, proc_info in enumerate(proc_infos):
            instance_name = f"{name}:{i}"
            status = "RUNNING" if proc_info.successfully_started else "STARTING"

            if proc_info.process.poll() is None:
                pid_str = str(proc_info.process.pid)
                uptime_val = int(time.time() - proc_info.start_time)
                uptime_str = f"{uptime_val}s"
                print(f"{instance_name:<{col_instance}} {status:<{col_state}} {pid_str:<{col_pid}} {uptime_str:<{col_uptime}} {proc_info.retry_count:<{col_retries}}")
            else:
                print(f"{instance_name:<{col_instance}} {'STOPPED':<{col_state}} {'-':<{col_pid}} {'-':<{col_uptime}} {proc_info.retry_count:<{col_retries}}")

    def status_all_jobs(self):
        """Show status of all programs"""
        # Use same column widths as individual status display
        col_instance = 20
        col_state = 12
        col_pid = 8
        col_uptime = 10
        col_retries = 8

        # Show status for all programs defined in config and any running jobs
        programs = sorted(set(list(self.config.keys()) + list(self.jobs.keys())))

        if not programs:
            print("\nNo programs configured or running")
            return

        print(f"\n{'Program':<{col_instance}} {'State':<{col_state}} {'PID':<{col_pid}} {'Uptime':<{col_uptime}} {'Retries':<{col_retries}}")
        print("-" * (col_instance + col_state + col_pid + col_uptime + col_retries + 4))

        for name in programs:
            proc_infos = self.jobs.get(name)
            # Not running but configured
            if not proc_infos:
                print(f"{name:<{col_instance}} {'STOPPED':<{col_state}} {'-':<{col_pid}} {'-':<{col_uptime}} {'-':<{col_retries}}")
                continue

            for i, proc_info in enumerate(proc_infos):
                instance_name = f"{name}:{i}" if len(proc_infos) > 1 else name
                status = "RUNNING" if proc_info.successfully_started else "STARTING"

                if proc_info.process.poll() is None:
                    pid_str = str(proc_info.process.pid)
                    uptime_val = int(time.time() - proc_info.start_time)
                    uptime_str = f"{uptime_val}s"
                    print(f"{instance_name:<{col_instance}} {status:<{col_state}} {pid_str:<{col_pid}} {uptime_str:<{col_uptime}} {proc_info.retry_count:<{col_retries}}")
                else:
                    print(f"{instance_name:<{col_instance}} {'STOPPED':<{col_state}} {'-':<{col_pid}} {'-':<{col_uptime}} {proc_info.retry_count:<{col_retries}}")
        print()

    def _start_single_process(self, name, program_cfg):
        """Start a single process instance"""
        cmd = program_cfg.get('cmd')
        if not cmd:
            print(f"No command for program '{name}'")
            return None
        
        # Get configuration
        env_vars = program_cfg.get('env', {})
        workdir = program_cfg.get('workingdir') or program_cfg.get('workdir') or os.getcwd()
        umask_val = program_cfg.get('umask', 0o022)
        
        if isinstance(umask_val, str):
            umask_val = int(umask_val, 8)

        # Prepare environment
        env = os.environ.copy()
        for key, value in env_vars.items():
            env[key] = str(value)
        # Force Python unbuffered
        env['PYTHONUNBUFFERED'] = '1'

        def setup():
            try:
                os.umask(umask_val)
                os.chdir(workdir)
            except Exception as e:
                print(f"Error in setup: {e}")

        # Handle stdout
        stdout_path = program_cfg.get('stdout')
        if stdout_path:
            stdout_path = Path(stdout_path)
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stdout = open(stdout_path, 'a', buffering=1)
        else:
            stdout = subprocess.DEVNULL
        
        # Handle stderr
        stderr_path = program_cfg.get('stderr')
        if stderr_path:
            stderr_path = Path(stderr_path)
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr = open(stderr_path, 'a', buffering=1)
        else:
            stderr = subprocess.DEVNULL

        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=stdout,
                stderr=stderr,
                preexec_fn=setup,
                env=env
            )
            return ProcessInfo(proc, time.time())
        except Exception as e:
            print(f"Failed to start: {e}")
            return None

    def start_job(self, name):
        """Start a program"""
        program_cfg = self.config.get(name)
        if not program_cfg:
            print(f"Program '{name}' not found in config")
            return
        
        # Check if already running
        if name in self.jobs:
            running_count = sum(1 for p in self.jobs[name] if p.process.poll() is None)
            expected_count = program_cfg.get('numprocs', 1)
            if running_count == expected_count:
                print(f"Program '{name}' already running ({running_count} instances)")
                return

        # Start processes
        numprocs = program_cfg.get('numprocs', 1)
        proc_infos = []
        
        for i in range(numprocs):
            proc_info = self._start_single_process(name, program_cfg)
            if proc_info:
                print(f"Started {name}:{i} with PID {proc_info.process.pid}")
                proc_infos.append(proc_info)
                # Log to file only
                if self.logger:
                    self.logger.info(f"Started {name}:{i} (PID {proc_info.process.pid})")
                else:
                    self.log(f"Started {name}:{i} (PID {proc_info.process.pid})")
        
        if proc_infos:
            self.jobs[name] = proc_infos

    def stop_job(self, name, silent=False):
        """Stop a program"""
        proc_infos = self.jobs.get(name)
        if not proc_infos:
            if not silent:
                print(f"Program '{name}' not running")
            return
        
        program_cfg = self.config.get(name, {})
        stopsignal = program_cfg.get('stopsignal', 'TERM')
        stoptime = program_cfg.get('stoptime', 10)
        
        sig = getattr(signal, f'SIG{stopsignal}', signal.SIGTERM)
        
        for i, proc_info in enumerate(proc_infos):
            if proc_info.process.poll() is None:
                try:
                    print(f"Stopping {name}:{i} (PID {proc_info.process.pid}) with SIG{stopsignal}")
                    os.kill(proc_info.process.pid, sig)
                    
                    # Wait for graceful shutdown
                    start = time.time()
                    while time.time() - start < stoptime:
                        if proc_info.process.poll() is not None:
                            print(f"{name}:{i} stopped gracefully")
                            # Log to file only
                            if self.logger:
                                self.logger.info(f"Stopped {name}:{i} gracefully")
                            break
                        time.sleep(0.1)
                    
                    # Force kill if needed
                    if proc_info.process.poll() is None:
                        print(f"{name}:{i} did not stop, force killing")
                        os.kill(proc_info.process.pid, signal.SIGKILL)
                        time.sleep(0.5)
                        # Log to file only
                        if self.logger:
                            self.logger.warning(f"Force killed {name}:{i}")

                    self.logger.error(f"Stopped {name}:{i} (PID {proc_info.process.pid})", True)
                except ProcessLookupError:
                    pass
        
        del self.jobs[name]

    def restart_job(self, name):
        """Restart a program"""
        print(f"Restarting {name}...")
        self.stop_job(name, silent=True)
        time.sleep(0.5)
        self.start_job(name)

    def stop_all_jobs(self):
        """Stop all programs"""
        for name in list(self.jobs.keys()):
            self.stop_job(name, silent=True)

    def reload_config(self):
        """Reload configuration"""
        if not self.config_path:
            print("No config file path")
            return
        
        try:
            new_config = load_config(self.config_path)
            print("Config file loaded")
            
            old_programs = set(self.config.keys())
            new_programs = set(new_config.keys())
            
            # Remove deleted programs
            for name in old_programs - new_programs:
                print(f"Removing: {name}")
                self.stop_job(name, silent=True)
            
            # Add new programs
            for name in new_programs - old_programs:
                print(f"Adding: {name}")
                self.config[name] = new_config[name]
                if new_config[name].get('autostart', False):
                    self.start_job(name)
            
            # Check existing programs for changes
            for name in old_programs & new_programs:
                old_cfg = self.config[name]
                new_cfg = new_config[name]
                
                # Fields that require restart
                critical_fields = ['cmd', 'numprocs', 'umask', 'workingdir', 
                                 'env', 'stdout', 'stderr']
                
                changed = False
                changes = []
                for field in critical_fields:
                    if old_cfg.get(field) != new_cfg.get(field):
                        changed = True
                        changes.append(f"{field}: {old_cfg.get(field)} -> {new_cfg.get(field)}")
                
                if changed:
                    print(f"\n'{name}' changed:")
                    for change in changes:
                        print(f"  - {change}")
                    print(f"Restarting {name}...\n")
                    
                    self.stop_job(name, silent=True)
                    time.sleep(0.5)
                    self.config[name] = new_cfg
                    self.start_job(name)
                else:
                    self.config[name] = new_cfg
                    print(f"'{name}': No changes")
            
            print("\nReload complete!")
            # Log to file only
            if self.logger:
                self.logger.info("Configuration reloaded")
            
        except Exception as e:
            print(f"Reload failed: {e}")
            import traceback
            traceback.print_exc()


def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <config_file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    config = load_config(file_path)
    
    # Validate if available
    if VALIDATOR_AVAILABLE:
        print("\nValidating configuration...")
        if not ConfigValidator.print_validation_report(config):
            response = input("\nContinue anyway? (y/n): ").strip().lower()
            if response != 'y':
                sys.exit(1)
        ConfigValidator.print_config_summary(config)
    
    try:
        manager = JobManager(config=config, config_path=file_path)
        monitor = ProcessMonitor(manager)
        monitor.start()
        
        print("\nTaskmaster running")
        if DASHBOARD_AVAILABLE:
            print("Dashboard: http://localhost:8080")
        print()
        
        ShellCommand(manager).cmdloop()
        
        if manager.dashboard:
            manager.dashboard.stop()
            
    except KeyboardInterrupt:
        print("\nExiting...")
        if 'manager' in locals():
            manager.stop_all_jobs()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)