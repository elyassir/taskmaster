#!/usr/bin/env python3
"""
Taskmaster Control Shell
Interactive command-line interface for controlling taskmaster
"""

import readline
import sys
import threading
import time


class ControlShell:
    """Interactive control shell for taskmaster"""
    
    def __init__(self, daemon):
        self.daemon = daemon
        self.running = True
        
        # Setup readline
        readline.parse_and_bind('tab: complete')
        readline.set_completer(self.completer)
        
        # Command history
        self.commands = [
            'status', 'start', 'stop', 'restart', 
            'reload', 'shutdown', 'help', 'quit', 'exit'
        ]
        
        # Start daemon monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_daemon, daemon=True)
        self.monitor_thread.start()
    
    def _monitor_daemon(self):
        """Monitor daemon in background thread"""
        while self.running and self.daemon.running:
            time.sleep(0.5)
    
    def completer(self, text, state):
        """Tab completion for commands"""
        options = [cmd for cmd in self.commands if cmd.startswith(text)]
        
        # Add program names for start/stop/restart commands
        if hasattr(self, 'last_command'):
            if self.last_command in ['start', 'stop', 'restart']:
                prog_names = list(self.daemon.processes.keys())
                options.extend([name for name in prog_names if name.startswith(text)])
        
        if state < len(options):
            return options[state]
        return None
    
    def run(self):
        """Main shell loop"""
        self.print_welcome()
        
        while self.running and self.daemon.running:
            try:
                line = input('taskmaster> ').strip()
                
                if not line:
                    continue
                
                parts = line.split()
                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []
                
                self.last_command = command
                self.execute_command(command, args)
                
            except EOFError:
                print()
                self.cmd_shutdown([])
                break
            except KeyboardInterrupt:
                print()
                continue
            except Exception as e:
                print(f"Error: {e}")
        
        # Ensure daemon stops
        if self.daemon.running:
            self.daemon.running = False
            self.daemon.shutdown()
    
    def print_welcome(self):
        """Print welcome message"""
        print("=" * 60)
        print("Taskmaster Control Shell")
        print("Type 'help' for available commands")
        print("=" * 60)
        print()
    
    def execute_command(self, command, args):
        """Execute a shell command"""
        cmd_map = {
            'status': self.cmd_status,
            'start': self.cmd_start,
            'stop': self.cmd_stop,
            'restart': self.cmd_restart,
            'reload': self.cmd_reload,
            'shutdown': self.cmd_shutdown,
            'quit': self.cmd_shutdown,
            'exit': self.cmd_shutdown,
            'help': self.cmd_help,
        }
        
        if command in cmd_map:
            cmd_map[command](args)
        else:
            print(f"Unknown command: {command}")
            print("Type 'help' for available commands")
    
    def cmd_status(self, args):
        """Display status of all programs"""
        if args and args[0] != 'all':
            # Status of specific program
            prog_name = args[0]
            if prog_name not in self.daemon.processes:
                print(f"Error: Unknown program '{prog_name}'")
                return
            
            proc_list = self.daemon.processes[prog_name]
        else:
            # Status of all programs
            proc_list = []
            for procs in self.daemon.processes.values():
                proc_list.extend(procs)
        
        if not proc_list:
            print("No programs configured")
            return
        
        # Print header
        print(f"{'PROGRAM':<25} {'STATE':<12} {'PID':<8} {'UPTIME':<10}")
        print("-" * 60)
        
        # Print process info
        for proc in proc_list:
            uptime = ""
            if proc.start_time and proc.is_alive():
                uptime = self._format_uptime(time.time() - proc.start_time)
            
            pid_str = str(proc.pid) if proc.pid else "-"
            
            print(f"{proc.get_full_name():<25} {proc.state:<12} {pid_str:<8} {uptime:<10}")
    
    def _format_uptime(self, seconds):
        """Format uptime in human-readable format"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds/60)}m {int(seconds%60)}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def cmd_start(self, args):
        """Start a program"""
        if not args:
            print("Usage: start <program_name>")
            return
        
        prog_name = args[0]
        
        if prog_name == 'all':
            # Start all programs
            for name in self.daemon.processes.keys():
                print(f"Starting {name}...")
                self.daemon.start_program(name)
        else:
            if prog_name not in self.daemon.processes:
                print(f"Error: Unknown program '{prog_name}'")
                return
            
            print(f"Starting {prog_name}...")
            if self.daemon.start_program(prog_name):
                print(f"{prog_name}: started")
            else:
                print(f"{prog_name}: failed to start")
    
    def cmd_stop(self, args):
        """Stop a program"""
        if not args:
            print("Usage: stop <program_name>")
            return
        
        prog_name = args[0]
        
        if prog_name == 'all':
            # Stop all programs
            for name in self.daemon.processes.keys():
                print(f"Stopping {name}...")
                self.daemon.stop_program(name)
        else:
            if prog_name not in self.daemon.processes:
                print(f"Error: Unknown program '{prog_name}'")
                return
            
            print(f"Stopping {prog_name}...")
            if self.daemon.stop_program(prog_name):
                print(f"{prog_name}: stopped")
            else:
                print(f"{prog_name}: failed to stop")
    
    def cmd_restart(self, args):
        """Restart a program"""
        if not args:
            print("Usage: restart <program_name>")
            return
        
        prog_name = args[0]
        
        if prog_name == 'all':
            # Restart all programs
            for name in self.daemon.processes.keys():
                print(f"Restarting {name}...")
                self.daemon.restart_program(name)
        else:
            if prog_name not in self.daemon.processes:
                print(f"Error: Unknown program '{prog_name}'")
                return
            
            print(f"Restarting {prog_name}...")
            if self.daemon.restart_program(prog_name):
                print(f"{prog_name}: restarted")
            else:
                print(f"{prog_name}: failed to restart")
    
    def cmd_reload(self, args):
        """Reload configuration file"""
        print("Reloading configuration...")
        if self.daemon.load_configuration():
            print("Configuration reloaded successfully")
        else:
            print("Failed to reload configuration")
    
    def cmd_shutdown(self, args):
        """Shutdown taskmaster"""
        print("Shutting down Taskmaster...")
        self.running = False
        self.daemon.running = False
    
    def cmd_help(self, args):
        """Display help information"""
        help_text = """
Available commands:

  status [program]     - Show status of all programs or a specific program
  start <program|all>  - Start a program or all programs
  stop <program|all>   - Stop a program or all programs
  restart <program|all>- Restart a program or all programs
  reload               - Reload configuration file
  shutdown             - Stop all programs and exit taskmaster
  quit/exit            - Same as shutdown
  help                 - Show this help message

Examples:
  status               - Show status of all programs
  status nginx         - Show status of nginx program
  start nginx          - Start nginx program
  stop all             - Stop all programs
  restart nginx        - Restart nginx program
  reload               - Reload configuration without stopping programs
"""
        print(help_text)


if __name__ == '__main__':
    print("This module should be imported by taskmaster.py")
    sys.exit(1)