"""
Configuration validator for Taskmaster
Validates YAML configuration and provides helpful error messages
"""

import os
import signal


class ConfigValidator:
    """Validates taskmaster configuration"""
    
    VALID_SIGNALS = [
        'TERM', 'INT', 'QUIT', 'KILL', 'HUP', 'USR1', 'USR2', 'ABRT'
    ]
    
    VALID_AUTORESTART = ['always', 'never', 'unexpected']
    
    @classmethod
    def validate(cls, config):
        """
        Validate the configuration dictionary
        Returns: (is_valid, errors_list)
        """
        errors = []
        
        if not isinstance(config, dict):
            return False, ["Configuration must be a dictionary"]
        
        if not config:
            return False, ["Configuration is empty - no programs defined"]
        
        for program_name, program_config in config.items():
            prog_errors = cls._validate_program(program_name, program_config)
            errors.extend(prog_errors)
        
        return len(errors) == 0, errors
    
    @classmethod
    def _validate_program(cls, name, config):
        """Validate a single program configuration"""
        errors = []
        
        # Check required fields
        if 'cmd' not in config:
            errors.append(f"Program '{name}': Missing required field 'cmd'")
        elif not config['cmd']:
            errors.append(f"Program '{name}': 'cmd' cannot be empty")
        
        # Validate numprocs
        if 'numprocs' in config:
            numprocs = config['numprocs']
            if not isinstance(numprocs, int) or numprocs < 1:
                errors.append(f"Program '{name}': 'numprocs' must be a positive integer")
            if numprocs > 100:
                errors.append(f"Program '{name}': Warning - 'numprocs' is very high ({numprocs})")
        
        # Validate umask
        if 'umask' in config:
            umask = config['umask']
            if isinstance(umask, str):
                try:
                    int(umask, 8)
                except ValueError:
                    errors.append(f"Program '{name}': 'umask' must be a valid octal number (e.g., '022')")
            elif isinstance(umask, int):
                if umask < 0 or umask > 0o777:
                    errors.append(f"Program '{name}': 'umask' must be between 0 and 0777")
        
        # Validate workingdir
        if 'workingdir' in config:
            workdir = config['workingdir']
            if workdir and not os.path.isdir(workdir):
                errors.append(f"Program '{name}': Working directory '{workdir}' does not exist")
        
        # Validate autostart
        if 'autostart' in config:
            if not isinstance(config['autostart'], bool):
                errors.append(f"Program '{name}': 'autostart' must be true or false")
        
        # Validate autorestart
        if 'autorestart' in config:
            autorestart = config['autorestart']
            if autorestart not in cls.VALID_AUTORESTART:
                errors.append(f"Program '{name}': 'autorestart' must be one of {cls.VALID_AUTORESTART}")
        
        # Validate exitcodes
        if 'exitcodes' in config:
            exitcodes = config['exitcodes']
            if isinstance(exitcodes, int):
                if exitcodes < 0 or exitcodes > 255:
                    errors.append(f"Program '{name}': Exit code must be between 0 and 255")
            elif isinstance(exitcodes, list):
                for code in exitcodes:
                    if not isinstance(code, int) or code < 0 or code > 255:
                        errors.append(f"Program '{name}': All exit codes must be integers between 0 and 255")
                        break
            else:
                errors.append(f"Program '{name}': 'exitcodes' must be an integer or list of integers")
        
        # Validate startretries
        if 'startretries' in config:
            retries = config['startretries']
            if not isinstance(retries, int) or retries < 0:
                errors.append(f"Program '{name}': 'startretries' must be a non-negative integer")
            if retries > 50:
                errors.append(f"Program '{name}': Warning - 'startretries' is very high ({retries})")
        
        # Validate starttime
        if 'starttime' in config:
            starttime = config['starttime']
            if not isinstance(starttime, (int, float)) or starttime < 0:
                errors.append(f"Program '{name}': 'starttime' must be a non-negative number")
        
        # Validate stopsignal
        if 'stopsignal' in config:
            stopsignal = config['stopsignal']
            if stopsignal not in cls.VALID_SIGNALS:
                errors.append(f"Program '{name}': 'stopsignal' must be one of {cls.VALID_SIGNALS}")
            
            # Check if signal exists on this system
            try:
                getattr(signal, f'SIG{stopsignal}')
            except AttributeError:
                errors.append(f"Program '{name}': Signal 'SIG{stopsignal}' not available on this system")
        
        # Validate stoptime
        if 'stoptime' in config:
            stoptime = config['stoptime']
            if not isinstance(stoptime, (int, float)) or stoptime < 0:
                errors.append(f"Program '{name}': 'stoptime' must be a non-negative number")
            if stoptime > 300:
                errors.append(f"Program '{name}': Warning - 'stoptime' is very high ({stoptime}s)")
        
        # Validate stdout/stderr paths
        for stream in ['stdout', 'stderr']:
            if stream in config and config[stream]:
                path = config[stream]
                directory = os.path.dirname(path)
                if directory and not os.path.isdir(directory):
                    errors.append(f"Program '{name}': Directory for '{stream}' does not exist: {directory}")
        
        # Validate environment variables
        if 'env' in config:
            env = config['env']
            if not isinstance(env, dict):
                errors.append(f"Program '{name}': 'env' must be a dictionary")
            else:
                for key, value in env.items():
                    if not isinstance(key, str):
                        errors.append(f"Program '{name}': Environment variable keys must be strings")
                        break
        
        return errors
    
    @classmethod
    def print_validation_report(cls, config):
        """Print a detailed validation report"""
        is_valid, errors = cls.validate(config)
        
        if is_valid:
            print("✓ Configuration is valid!")
            print(f"✓ Found {len(config)} program(s)")
            return True
        else:
            print("✗ Configuration validation failed:")
            print()
            for error in errors:
                print(f"  • {error}")
            print()
            print(f"Found {len(errors)} error(s)")
            return False
    
    @classmethod
    def get_config_summary(cls, config):
        """Get a summary of the configuration"""
        summary = {
            'total_programs': len(config),
            'autostart_programs': 0,
            'total_processes': 0,
            'programs': []
        }
        
        for name, prog_config in config.items():
            if prog_config.get('autostart', False):
                summary['autostart_programs'] += 1
            
            numprocs = prog_config.get('numprocs', 1)
            summary['total_processes'] += numprocs
            
            summary['programs'].append({
                'name': name,
                'numprocs': numprocs,
                'autostart': prog_config.get('autostart', False),
                'autorestart': prog_config.get('autorestart', 'never')
            })
        
        return summary
    
    @classmethod
    def print_config_summary(cls, config):
        """Print a summary of the configuration"""
        summary = cls.get_config_summary(config)
        
        print("\n" + "="*50)
        print("Configuration Summary")
        print("="*50)
        print(f"Total programs: {summary['total_programs']}")
        print(f"Autostart programs: {summary['autostart_programs']}")
        print(f"Total processes: {summary['total_processes']}")
        print()
        print("Programs:")
        for prog in summary['programs']:
            autostart = "✓" if prog['autostart'] else "✗"
            print(f"  {autostart} {prog['name']}: {prog['numprocs']} instance(s), restart={prog['autorestart']}")
        print("="*50 + "\n")