"""
Enhanced logging module for Taskmaster
Provides file logging, console logging, and optional email alerts
"""

import logging
import logging.handlers
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class TaskmasterLogger:
    """Enhanced logger with file rotation and email alerts"""
    
    def __init__(self, log_file='taskmaster.log', email_config=None):
        self.logger = logging.getLogger('taskmaster')
        self.logger.setLevel(logging.INFO)
        
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # File handler with rotation (10MB max, keep 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,
            backupCount=5
        )
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        

        self.email_config = email_config
        
    def info(self, message):
        """Log info message"""
        self.logger.info(message)
    
    def warning(self, message):
        """Log warning message"""
        self.logger.warning(message)
    
    def error(self, message, send_email=False):
        """Log error message and optionally send email alert"""
        self.logger.error(message)
        if send_email and self.email_config:
            self._send_email_alert(message, 'STOPPED')
    
    def critical(self, message, send_email=True):
        """Log critical message and send email alert"""
        self.logger.critical(message)
        if send_email and self.email_config:
            self._send_email_alert(message, 'CRITICAL')
    
    def _send_email_alert(self, message, level):
        """Send email alert for critical events"""
        self.logger.info(f"Send email alert for critical events:)")
        if not self.email_config:
            print("Email configuration not provided, cannot send alert")
            return
        try:
            
            smtp_server = self.email_config.get('smtp_server')
            smtp_port = self.email_config.get('smtp_port', 587)
            username = self.email_config.get('username')
            password = self.email_config.get('password')
            from_addr = self.email_config.get('from_addr')
            to_addrs = self.email_config.get('to_addrs', [])
            
            if not all([smtp_server, username, password, from_addr, to_addrs]):
                return
            
            msg = MIMEMultipart()
            msg['From'] = from_addr
            msg['To'] = ', '.join(to_addrs)
            msg['Subject'] = f'Taskmaster Alert - {level}'
            
            body = f"""
Taskmaster Alert
================
Level: {level}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Message: {message}
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
            server.quit()
            
            self.logger.info(f"Email alert sent to {to_addrs}")
            
        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")

    def log_process_event(self, program_name, event_type, details=''):
        """Log process-related events"""
        message = f"Program '{program_name}' - {event_type}"
        if details:
            message += f" - {details}"
        
        # Send email for fatal conditions and when a program stops
        if event_type in ['FATAL', 'CRASH', 'MAX_RETRIES']:
            self.error(message, send_email=True)
        elif event_type == 'STOPPED':
            self.error(message, send_email=True)
        elif event_type in ['STARTED', 'RESTARTED']:
            self.info(message)
        else:
            self.warning(message)


# Global logger instance
_logger = None

def get_logger(log_file='taskmaster.log', email_config=None):
    """Get or create global logger instance"""
    global _logger
    if _logger is None:
        _logger = TaskmasterLogger(log_file, email_config)
    return _logger