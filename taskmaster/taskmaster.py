#!/usr/bin/env python3
"""
Taskmaster - Job Control Daemon
Main program file
"""

import os
import sys
import signal
import time
import subprocess
import yaml
import logging
from datetime import datetime
from collections import defaultdict
import select

class ProcessInfo:
    """Stores information about a supervised process"""
    
    STOPPED = 'STOPPED'
    STARTING = 'STARTING'
    RUNNING = 'RUNNING'
    BACKOFF = 'BACKOFF'
    STOPPING = 'STOPPING'
    EXITED = 'EXITED'
    FATAL = 'FATAL'
    UNKNOWN = 'UNKNOWN'
    
    def __init__(self, name, config, instance_num=0):
        self.name = name
        self.instance_num = instance_num
        self.config = config
        self.process = None
        self.pid = None
        self.state = self.STOPPED
        self.start_time = None
        self.stop_time = None
        self.retry_count = 0
        self.last_exit_code = None
        
    def get_full_name(self):
        """Returns the full process name with instance number"""
        if self.config.get('numprocs', 1) > 1:
            return f"{self.name}:{self.instance_num}"
        return self.name
    
    def is_alive(self):
        """Check if process is actually running"""
        if self.process is None:
            return False
        return self.process.poll() is None


class TaskmasterConfig:
    """Handles configuration file parsing and validation"""
    
    def __init__(self, config_file):
        self.config_file = config_file
        self.programs = {}
        self.load()
    
    def load(self):
        """Load and parse configuration file"""
        try:
            with open(self.config_file, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data or 'programs' not in data:
                raise ValueError("Configuration must contain 'programs' section")
            
            self.programs = {}
            for name, config in data['programs'].items():
                self.programs[name] = self._validate_config(name, config)
            
            return True
        except Exception as e:
            logging.error(f"Failed to load configuration: {e}")
            return False
    
    def _validate_config(self, name, config):
        """Validate and set defaults for program configuration"""
        validated = {
            'cmd': config.get('cmd', ''),
            'numprocs': config.get('numprocs', 1),
            'umask': config.get('umask', None),
            'workingdir': config.get('workingdir', None),
            'autostart': config.get('autostart', True),
            'autorestart': config.get('autorestart', 'unexpected'),
            'exitcodes': config.get('exitcodes', [0]),
            'startretries': config.get('startretries', 3),
            'starttime': config.get('starttime', 1),
            'stopsignal': config.get('stopsignal', 'TERM'),
            'stoptime': config.get('stoptime', 10),
            'stdout': config.get('stdout', None),
            'stderr': config.get('stderr', None),
            'env': config.get('env', {}),
        }
        
        if not validated['cmd']:
            raise ValueError(f"Program '{name}' must have a 'cmd' specified")
        
        # Ensure exitcodes is a list
        if isinstance(validated['exitcodes'], int):
            validated['exitcodes'] = [validated['exitcodes']]
        
        return validated


class Taskmaster:
    """Main taskmaster daemon"""
    
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = None
        self.processes = {}  # name -> list of ProcessInfo
        self.running = True
        self.reload_requested = False
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('taskmaster.log'),
                logging.StreamHandler()
            ]
        )
        
        # Setup signal handlers
        signal.signal(signal.SIGHUP, self._handle_sighup)
        signal.signal(signal.SIGINT, self._handle_sigint)
        signal.signal(signal.SIGTERM, self._handle_sigint)
        signal.signal(signal.SIGCHLD, self._handle_sigchld)
    
    def _handle_sighup(self, signum, frame):
        """Handle SIGHUP - reload configuration"""
        logging.info("Received SIGHUP, reloading configuration")
        self.reload_requested = True
    
    def _handle_sigint(self, signum, frame):
        """Handle SIGINT/SIGTERM - graceful shutdown"""
        logging.info("Received shutdown signal")
        self.running = False
    
    def _handle_sigchld(self, signum, frame):
        """Handle SIGCHLD - child process died"""
        # Reap zombie processes
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                self._handle_process_exit(pid, status)
            except ChildProcessError:
                break
    
    def _handle_process_exit(self, pid, status):
        """Handle a process exit"""
        # Find the process
        for prog_name, proc_list in self.processes.items():
            for proc in proc_list:
                if proc.pid == pid:
                    if os.WIFEXITED(status):
                        exit_code = os.WEXITSTATUS(status)
                        proc.last_exit_code = exit_code
                        logging.info(f"Process {proc.get_full_name()} (PID {pid}) exited with code {exit_code}")
                    elif os.WIFSIGNALED(status):
                        signal_num = os.WTERMSIG(status)
                        proc.last_exit_code = -signal_num
                        logging.info(f"Process {proc.get_full_name()} (PID {pid}) killed by signal {signal_num}")
                    
                    proc.process = None
                    proc.pid = None
                    proc.state = ProcessInfo.EXITED
                    return
    
    def start(self):
        """Start the taskmaster daemon"""
        logging.info("Starting Taskmaster")
        
        # Load initial configuration
        if not self.load_configuration():
            logging.error("Failed to load initial configuration")
            return False
        
        # Start autostart programs
        self.start_autostart_programs()
        
        return True
    
    def load_configuration(self):
        """Load or reload configuration"""
        new_config = TaskmasterConfig(self.config_file)
        
        if not new_config.programs:
            return False
        
        if self.config is None:
            # Initial load
            self.config = new_config
            self._initialize_processes()
        else:
            # Reload
            self._reload_configuration(new_config)
        
        return True
    
    def _initialize_processes(self):
        """Initialize process structures from configuration"""
        self.processes = {}
        for prog_name, prog_config in self.config.programs.items():
            num_procs = prog_config['numprocs']
            self.processes[prog_name] = []
            for i in range(num_procs):
                proc_info = ProcessInfo(prog_name, prog_config, i)
                self.processes[prog_name].append(proc_info)
    
    def _reload_configuration(self, new_config):
        """Reload configuration and update running processes"""
        old_programs = set(self.config.programs.keys())
        new_programs = set(new_config.programs.keys())
        
        # Remove deleted programs
        for prog_name in old_programs - new_programs:
            logging.info(f"Removing program: {prog_name}")
            self.stop_program(prog_name)
            del self.processes[prog_name]
        
        # Add new programs
        for prog_name in new_programs - old_programs:
            logging.info(f"Adding program: {prog_name}")
            prog_config = new_config.programs[prog_name]
            num_procs = prog_config['numprocs']
            self.processes[prog_name] = []
            for i in range(num_procs):
                proc_info = ProcessInfo(prog_name, prog_config, i)
                self.processes[prog_name].append(proc_info)
            
            if prog_config['autostart']:
                self.start_program(prog_name)
        
        # Update existing programs
        for prog_name in old_programs & new_programs:
            old_config = self.config.programs[prog_name]
            new_prog_config = new_config.programs[prog_name]
            
            # Check if configuration changed
            if old_config != new_prog_config:
                logging.info(f"Updating program: {prog_name}")
                # For simplicity, stop and restart with new config
                self.stop_program(prog_name)
                
                # Update process list for new numprocs
                num_procs = new_prog_config['numprocs']
                self.processes[prog_name] = []
                for i in range(num_procs):
                    proc_info = ProcessInfo(prog_name, new_prog_config, i)
                    self.processes[prog_name].append(proc_info)
                
                if new_prog_config['autostart']:
                    self.start_program(prog_name)
        
        self.config = new_config
        logging.info("Configuration reloaded successfully")
    
    def start_autostart_programs(self):
        """Start all programs marked with autostart"""
        for prog_name, prog_config in self.config.programs.items():
            if prog_config['autostart']:
                self.start_program(prog_name)
    
    def start_program(self, prog_name):
        """Start a program (all instances)"""
        if prog_name not in self.processes:
            logging.error(f"Unknown program: {prog_name}")
            return False
        
        success = True
        for proc in self.processes[prog_name]:
            if not self._start_process(proc):
                success = False
        
        return success
    
    def _start_process(self, proc):
        """Start a single process instance"""
        if proc.state in [ProcessInfo.RUNNING, ProcessInfo.STARTING]:
            logging.warning(f"Process {proc.get_full_name()} already running")
            return False
        
        config = proc.config
        
        try:
            # Prepare environment
            env = os.environ.copy()
            if config['env']:
                env.update(config['env'])
            
            # Prepare stdout/stderr
            stdout_file = None
            stderr_file = None
            
            if config['stdout']:
                stdout_file = open(config['stdout'], 'a')
            else:
                stdout_file = subprocess.DEVNULL
            
            if config['stderr']:
                stderr_file = open(config['stderr'], 'a')
            else:
                stderr_file = subprocess.DEVNULL
            
            # Set working directory
            cwd = config['workingdir'] if config['workingdir'] else None
            
            # Start process
            proc.process = subprocess.Popen(
                config['cmd'],
                shell=True,
                stdout=stdout_file,
                stderr=stderr_file,
                env=env,
                cwd=cwd,
                preexec_fn=lambda: self._setup_child_process(config)
            )
            
            proc.pid = proc.process.pid
            proc.state = ProcessInfo.STARTING
            proc.start_time = time.time()
            proc.retry_count = 0
            
            logging.info(f"Started process {proc.get_full_name()} with PID {proc.pid}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to start {proc.get_full_name()}: {e}")
            proc.state = ProcessInfo.FATAL
            return False
    
    def _setup_child_process(self, config):
        """Setup child process environment (called in child)"""
        if config['umask'] is not None:
            os.umask(int(str(config['umask']), 8))
    
    def stop_program(self, prog_name):
        """Stop a program (all instances)"""
        if prog_name not in self.processes:
            logging.error(f"Unknown program: {prog_name}")
            return False
        
        for proc in self.processes[prog_name]:
            self._stop_process(proc)
        
        return True
    
    def _stop_process(self, proc):
        """Stop a single process instance"""
        if proc.state == ProcessInfo.STOPPED:
            return True
        
        if not proc.is_alive():
            proc.state = ProcessInfo.STOPPED
            return True
        
        config = proc.config
        sig_name = config['stopsignal']
        stop_signal = getattr(signal, f"SIG{sig_name}", signal.SIGTERM)
        
        try:
            logging.info(f"Stopping process {proc.get_full_name()} (PID {proc.pid})")
            proc.state = ProcessInfo.STOPPING
            proc.stop_time = time.time()
            
            os.kill(proc.pid, stop_signal)
            
            # Wait for graceful shutdown
            for _ in range(config['stoptime']):
                if not proc.is_alive():
                    proc.state = ProcessInfo.STOPPED
                    logging.info(f"Process {proc.get_full_name()} stopped gracefully")
                    return True
                time.sleep(1)
            
            # Force kill
            logging.warning(f"Force killing process {proc.get_full_name()}")
            os.kill(proc.pid, signal.SIGKILL)
            time.sleep(1)
            
            proc.state = ProcessInfo.STOPPED
            return True
            
        except ProcessLookupError:
            proc.state = ProcessInfo.STOPPED
            return True
        except Exception as e:
            logging.error(f"Error stopping {proc.get_full_name()}: {e}")
            return False
    
    def restart_program(self, prog_name):
        """Restart a program"""
        self.stop_program(prog_name)
        time.sleep(1)
        return self.start_program(prog_name)
    
    def get_status(self):
        """Get status of all programs"""
        status = []
        for prog_name, proc_list in self.processes.items():
            for proc in proc_list:
                uptime = ""
                if proc.start_time and proc.is_alive():
                    uptime = f"{int(time.time() - proc.start_time)}s"
                
                status.append({
                    'name': proc.get_full_name(),
                    'state': proc.state,
                    'pid': proc.pid,
                    'uptime': uptime
                })
        return status
    
    def monitor_processes(self):
        """Monitor all processes and handle restarts"""
        for prog_name, proc_list in self.processes.items():
            for proc in proc_list:
                self._monitor_process(proc)
    
    def _monitor_process(self, proc):
        """Monitor a single process"""
        config = proc.config
        
        # Check if starting process became running
        if proc.state == ProcessInfo.STARTING:
            if proc.start_time and (time.time() - proc.start_time) >= config['starttime']:
                if proc.is_alive():
                    proc.state = ProcessInfo.RUNNING
                    logging.info(f"Process {proc.get_full_name()} successfully started")
                else:
                    logging.warning(f"Process {proc.get_full_name()} died during startup")
                    proc.state = ProcessInfo.BACKOFF
        
        # Check if process needs restart
        if proc.state in [ProcessInfo.EXITED, ProcessInfo.BACKOFF]:
            should_restart = False
            
            if config['autorestart'] == 'always':
                should_restart = True
            elif config['autorestart'] == 'unexpected':
                if proc.last_exit_code not in config['exitcodes']:
                    should_restart = True
            
            if should_restart:
                if proc.retry_count < config['startretries']:
                    proc.retry_count += 1
                    logging.info(f"Restarting {proc.get_full_name()} (attempt {proc.retry_count})")
                    time.sleep(1)
                    self._start_process(proc)
                else:
                    logging.error(f"Process {proc.get_full_name()} failed to start after {config['startretries']} attempts")
                    proc.state = ProcessInfo.FATAL
            else:
                proc.state = ProcessInfo.STOPPED
    
    def shutdown(self):
        """Shutdown taskmaster and stop all processes"""
        logging.info("Shutting down Taskmaster")
        
        for prog_name in list(self.processes.keys()):
            self.stop_program(prog_name)
        
        logging.info("Taskmaster stopped")
    
    def run(self):
        """Main loop"""
        while self.running:
            # Handle reload request
            if self.reload_requested:
                self.load_configuration()
                self.reload_requested = False
            
            # Monitor processes
            self.monitor_processes()
            
            # Sleep briefly
            time.sleep(0.5)
        
        self.shutdown()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <config_file>")
        sys.exit(1)
    
    config_file = sys.argv[1]
    
    if not os.path.exists(config_file):
        print(f"Configuration file not found: {config_file}")
        sys.exit(1)
    
    daemon = Taskmaster(config_file)
    
    if daemon.start():
        # Start control shell in main process
        from taskmasterctl import ControlShell
        shell = ControlShell(daemon)
        shell.run()
    else:
        print("Failed to start Taskmaster")
        sys.exit(1)