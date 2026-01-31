import yaml
import os
import sys
import subprocess
import cmd


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

"""

proc = subprocess.Popen(
    ["sleep", "60"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

pid = fork();
if (pid == 0) execvp(...);

"""

"""
if proc.poll() is None:
    print("Process still running")
else:
    print("Process exited with code", proc.returncode)

    
proc.terminate()

kill <pid>


"""

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
    def __init__(self, config):
        self.config = config
        self.jobs = {}

    def status_jobs(self, name):
        proc = self.jobs.get(name)
        if not proc:
            print(f"No running job found for program '{name}'.")
            return
        
        if proc.poll() is None:
            print(f"Program '{name}' is running with PID {proc.pid}.")
        else:
            print(f"Program '{name}' has exited with code {proc.returncode}.")
            del self.jobs[name]

    def status_all_jobs(self):
        for name, proc in self.jobs.items():
            if proc.poll() is None:
                print(f"Program '{name}' is running with PID {proc.pid}.")
            else:
                print(f"Program '{name}' has exited with code {proc.returncode}.")

    def start_job(self, name):
        program_cfg = self.config.get(name)
        if not program_cfg:
            print(f"No configuration found for program '{name}'.")
            return
        
        cmd = program_cfg.get('cmd')
        if not cmd:
            print(f"No command specified for program '{name}'.")
            return
        
        proc = subprocess.Popen(
            cmd.split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"Started program '{name}' with PID {proc.pid}.")

        self.jobs[name] = proc

    def stop_job(self, name):
        proc = self.jobs.get(name)
        if not proc:
            print(f"No running job found for program '{name}'.")
            return
        
        proc.terminate()
        print(f"Stopped program '{name}' with PID {proc.pid}.")
        del self.jobs[name]

def main():
    if (len(sys.argv) != 2):
        raise ValueError("Usage: python main.py <config_file_path>")
    file_path = sys.argv[1]
    config = load_config(file_path)
    print("Configuration loaded successfully.")

    ShellCommand(JobManager(config=config)).cmdloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error loading configuration: {e}")
        exit(1)
