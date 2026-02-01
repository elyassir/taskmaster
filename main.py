from pathlib import Path
import yaml
import os
import sys
import subprocess
import cmd
import threading
import time
from threading import Lock


class ProcessMonitor(threading.Thread):
    """Thread that monitors the status of all jobs"""
    def __init__(self, job_manager, interval=1):
        super().__init__(daemon=True)
        self.job_manager = job_manager
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self):
        print("Monitor started")
        while not self.stop_event.is_set():
            self.check_jobs()
            time.sleep(self.interval)

    def stop(self):
        self.stop_event.set()


    def check_jobs(self):
        with self.job_manager.lock:  
            for name, procs in list(self.job_manager.jobs.items()):
                for i, p in enumerate(procs):
                    if p.poll() is not None:
                        program_cfg = self.job_manager.config.get(name)
                        autorestart = program_cfg.get('autorestart', 'never') if program_cfg else 'never'
                        
                        print(f"Program '{name}' has exited with code {p.returncode}.")
                        if autorestart == "always":
                            print(f"Auto-restarting '{name}'...")
                            self.job_manager.restart_job(name)
                        elif autorestart == "unexpected":
                            exitcodes = program_cfg.get('exitcodes', [0]) if program_cfg else [0]
                            if p.returncode not in exitcodes:
                                print(f"Auto-restarting '{name}'...")
                                self.job_manager.restart_job(name)
                        else:
                            del self.job_manager.jobs[name]
                            break




# It inherits from cmd.Cmd
"""
This means:

Your class gets all the features of a command shell

You can type commands and handle them
"""

class ShellCommand(cmd.Cmd):
    intro = "Welcome to Taskmaster. Type help or ? to list commands.\n"
    prompt = "taskmaster> "

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def do_hello(self, arg):
        """Say hello"""
        print(f"Hello {arg or 'there'}!")

    def do_exit(self, arg):
        """Exit the shell"""
        self.manager.stop_all_jobs()
        print("Bye!")
        return True  
    
    def do_start(self, arg):
        """Start a specific program: start <name>"""
        if not arg:
            print("Error: start requires a program name.")
            return
        self.manager.start_job(arg)

    def do_stop(self, arg):
        """Stop a specific program: stop <name>"""
        if not arg:
            print("Error: stop requires a program name.")
            return
        self.manager.stop_job(arg)

    def do_status(self, arg):
        """Get status of a specific program: status <name>"""
        if not arg:
            self.manager.status_all_jobs()
        else:
            self.manager.status_jobs(arg)

    def do_restart(self, arg):
        """Restart a specific program: restart <name>"""
        if not arg:
            print("Error: restart requires a program name.")
            return
        self.manager.restart_job(arg)

    def do_reload(self, arg):
        """Reload the configuration file without stopping running programs"""
        self.manager.reload_config()

    def do_quit(self, arg):
        """Quit the taskmaster (alias for exit)"""
        return self.do_exit(arg)

def load_config(file_path):
    """Parse a YAML configuration file, returning the contents as a dictionary."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file {file_path} does not exist.")
    
    with open(file_path, 'r') as stream:
            try:
                # FullLoader is safer for loading untrusted input
                config_data = yaml.load(stream, Loader=yaml.FullLoader)
                return config_data.get('programs', {})
            except yaml.YAMLError as exc:
                print(f"Error parsing YAML: {exc}")
                exit(1)

class JobManager:
    def __init__(self, config, config_path=None):
        self.lock = Lock()
        self.config = config
        self.config_path = config_path
        self.jobs = {}
        self.auto_start_jobs()

    def auto_start_jobs(self):
        for name, program_cfg in self.config.items():
            if program_cfg.get('autostart', False):
                self.start_job(name)

    def status_jobs(self, name):
        proc = self.jobs.get(name)
        if not proc:
            print(f"No running job found for program '{name}'.")
            return
        for i, p in enumerate(proc):
            if p.poll() is None:
                print(f"Program '{name}' is running with PID {p.pid}.")
            else:
                print(f"Program '{name}' has exited with code {p.returncode}.")

    def status_all_jobs(self):
        for name, proc in self.jobs.items():
            for i, p in enumerate(proc):
                if p.poll() is None:
                    print(f"Program '{name}' is running with PID {p.pid}.")
                else:
                    print(f"Program '{name}' has exited with code {p.returncode}.")

    def start_job(self, name):
        program_cfg = self.config.get(name)
        if not program_cfg:
            print(f"No configuration found for program '{name}'.")
            return
        
        # Check if already running including numprocs
        existing_proc = self.jobs.get(name)
        if existing_proc and len(existing_proc) == program_cfg.get('numprocs', 1) and all(p.poll() is None for p in existing_proc):
            print(f"Program '{name}' is already running with PID {existing_proc[0].pid}.")
            return

        cmd = program_cfg.get('cmd')
        if not cmd:
            print(f"No command specified for program '{name}'.")
            return
        
        env = program_cfg.get('env') or {} 
        workdir = program_cfg.get('workdir') or os.getcwd()
        umask = program_cfg.get('umask') or 0o022

        def setup():
            os.umask(umask)
            os.chdir(workdir)
            os.environ.update(env)

        stdout_path = Path(program_cfg.get('stdout') or subprocess.DEVNULL)
        stderr_path = Path(program_cfg.get('stderr') or subprocess.DEVNULL)

        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)

        if not stdout_path.exists():
            stdout_path.touch()
        if not stderr_path.exists():
            stderr_path.touch()
        procs = [subprocess.Popen(
            cmd.split(),
            stdout=open(stdout_path, 'a'),
            stderr=open(stderr_path, 'a'),
            preexec_fn=setup
        ) for _ in range(program_cfg.get('numprocs', 1))]
        
        for i, p in enumerate(procs):
            print(f"Started program '{name}' with PID {p.pid}.")

        self.jobs[name] = procs

    def stop_job(self, name, silent=False):
        procs = self.jobs.get(name)
        if not procs:
            if not silent:
                print(f"No running job found for program '{name}'.")
            return
        
        for i, p in enumerate(procs):
            p.terminate()
            print(f"Stopped program '{name}' with PID {p.pid}.")
        del self.jobs[name]
        return True

    def restart_job(self, name):
        """Restart a job - stop if running, then start"""
        self.stop_job(name, silent=True)
        self.start_job(name)

    def stop_all_jobs(self):
        for name in list(self.jobs.keys()):
            self.stop_job(name)

def main():
    if (len(sys.argv) != 2):
        raise ValueError("Usage: python main.py <config_file_path>")
    file_path = sys.argv[1]
    config = load_config(file_path)
    print("Configuration loaded successfully.")

    try:
        manager = JobManager(config=config, config_path=file_path)
        monitor = ProcessMonitor(manager)
        monitor.start()
        ShellCommand(manager).cmdloop()
    except KeyboardInterrupt:
        print("\nGoodbye!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error loading configuration: {e}")
        exit(1)
