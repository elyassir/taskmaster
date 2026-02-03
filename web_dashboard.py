import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the dashboard interface"""
    
    job_manager = None  # Set by WebDashboard on initialization
    
    # Route mapping
    ROUTES = {
        '/': 'serve_html',
        '/api/status': 'serve_status_json',
        '/api/programs': 'serve_programs_json'
    }
    
    def do_GET(self):
        """Handle incoming GET requests"""
        path = urlparse(self.path).path
        handler_method = self.ROUTES.get(path)
        
        if handler_method:
            getattr(self, handler_method)()
        else:
            self.send_error(404, "Not Found")
    
    def serve_html(self):
        """Serve the main dashboard HTML page"""
        html_content = self._get_dashboard_html()
        self._send_response(200, 'text/html', html_content.encode())
    
    def serve_status_json(self):
        """Serve process status as JSON"""
        if not self.job_manager:
            self.send_error(500, "Job manager not initialized")
            return
        
        status_data = self._collect_status_data()
        self._send_response(200, 'application/json', json.dumps(status_data).encode())
    
    def serve_programs_json(self):
        """Serve list of configured programs as JSON"""
        if not self.job_manager:
            self.send_error(500, "Job manager not initialized")
            return
        
        programs = {'programs': list(self.job_manager.config.keys())}
        self._send_response(200, 'application/json', json.dumps(programs).encode())
    
    def _collect_status_data(self):
        """Collect current status of all programs"""
        status_list = []
        all_programs = sorted(set(
            list(self.job_manager.config.keys()) + 
            list(self.job_manager.jobs.keys())
        ))
        
        with self.job_manager.lock:
            for program_name in all_programs:
                proc_infos = self.job_manager.jobs.get(program_name)
                
                if not proc_infos:
                    # Program configured but not running
                    status_list.append(self._create_status_entry(program_name))
                else:
                    # Running instances
                    for instance_num, proc_info in enumerate(proc_infos):
                        status_list.append(
                            self._create_status_entry(program_name, instance_num, proc_info)
                        )
        
        return status_list
    
    def _create_status_entry(self, name, instance=None, proc_info=None):
        """Create a status entry for a program/instance"""
        if proc_info is None:
            # Stopped program
            return {
                'name': name,
                'instance': '-',
                'status': 'STOPPED',
                'pid': None,
                'uptime': 0,
                'retries': 0
            }
        
        # Running or exited program
        is_running = proc_info.process.poll() is None
        uptime = int(time.time() - proc_info.start_time) if is_running else 0
        
        if is_running:
            status = "RUNNING" if proc_info.successfully_started else "STARTING"
            pid = proc_info.process.pid
        else:
            status = "STOPPED"
            pid = None
        
        return {
            'name': name,
            'instance': instance,
            'status': status,
            'pid': pid,
            'uptime': uptime,
            'retries': proc_info.retry_count
        }
    
    def _send_response(self, status_code, content_type, data):
        """Send HTTP response with error handling"""
        try:
            self.send_response(status_code)
            self.send_header('Content-type', content_type)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected - ignore
            pass
        except Exception as e:
            # Log unexpected errors but don't crash
            print(f"Error sending response: {e}")
    
    def log_message(self, format, *args):
        """Suppress request logging to keep terminal clean"""
        pass
    
    @staticmethod
    def _get_dashboard_html():
        """Return the HTML content for the dashboard"""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Taskmaster Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
        }
        
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 32px;
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 10px;
        }
        
        .refresh-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .refresh-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        .refresh-btn:active {
            transform: translateY(0);
        }
        
        .last-update {
            color: #666;
            font-size: 14px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        th, td {
            padding: 14px 12px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }
        
        th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 0.5px;
        }
        
        th:first-child {
            border-radius: 6px 0 0 0;
        }
        
        th:last-child {
            border-radius: 0 6px 0 0;
        }
        
        tr {
            transition: background-color 0.2s;
        }
        
        tr:hover {
            background-color: #f8f9fa;
        }
        
        .status {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .status.running {
            background-color: #d4edda;
            color: #155724;
        }
        
        .status.starting {
            background-color: #fff3cd;
            color: #856404;
        }
        
        .status.stopped {
            background-color: #e2e3e5;
            color: #383d41;
        }
        
        .status.exited {
            background-color: #f8d7da;
            color: #721c24;
        }
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }
        
        .error-state {
            text-align: center;
            padding: 40px;
            color: #d32f2f;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 20px;
            }
            
            h1 {
                font-size: 24px;
            }
            
            table {
                font-size: 14px;
            }
            
            th, td {
                padding: 10px 8px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>Taskmaster Dashboard</h1>
                <div class="last-update" id="lastUpdate">Loading...</div>
            </div>
            <button class="refresh-btn" onclick="loadStatus()">🔄 Refresh</button>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Program</th>
                    <th>Instance</th>
                    <th>Status</th>
                    <th>PID</th>
                    <th>Uptime</th>
                    <th>Retries</th>
                </tr>
            </thead>
            <tbody id="statusBody">
                <tr>
                    <td colspan="6" class="loading">Loading data...</td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <script>
        const API_ENDPOINT = '/api/status';
        const REFRESH_INTERVAL = 5000; // 5 seconds
        
        function loadStatus() {
            fetch(API_ENDPOINT)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    updateTable(data);
                    updateLastUpdateTime();
                })
                .catch(error => {
                    console.error('Error loading status:', error);
                    showError('Failed to load status data');
                });
        }
        
        function updateTable(programs) {
            const tbody = document.getElementById('statusBody');
            
            if (!programs || programs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No programs configured</td></tr>';
                return;
            }
            
            tbody.innerHTML = programs.map(prog => createTableRow(prog)).join('');
        }
        
        function createTableRow(prog) {
            const pid = prog.pid !== null ? prog.pid : '-';
            const instance = prog.instance !== null && prog.instance !== '-' ? prog.instance : '-';
            const uptime = formatUptime(prog.uptime);
            
            return `
                <tr>
                    <td><strong>${escapeHtml(prog.name)}</strong></td>
                    <td>${instance}</td>
                    <td><span class="status ${prog.status.toLowerCase()}">${prog.status}</span></td>
                    <td>${pid}</td>
                    <td>${uptime}</td>
                    <td>${prog.retries}</td>
                </tr>
            `;
        }
        
        function formatUptime(seconds) {
            if (seconds === 0) return '-';
            if (seconds < 60) return `${seconds}s`;
            if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
            
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${minutes}m`;
        }
        
        function updateLastUpdateTime() {
            const now = new Date();
            const timeString = now.toLocaleTimeString();
            document.getElementById('lastUpdate').textContent = `Last updated: ${timeString}`;
        }
        
        function showError(message) {
            const tbody = document.getElementById('statusBody');
            tbody.innerHTML = `<tr><td colspan="6" class="error-state">${escapeHtml(message)}</td></tr>`;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Auto-refresh
        setInterval(loadStatus, REFRESH_INTERVAL);
        
        // Initial load
        loadStatus();
    </script>
</body>
</html>
        """


class WebDashboard:
    """Web dashboard server for Taskmaster"""
    
    DEFAULT_PORT = 8080
    
    def __init__(self, job_manager, port=None):
        """
        Initialize the web dashboard
        
        Args:
            job_manager: Reference to the JobManager instance
            port: Port number to run server on (default: 8080)
        """
        self.job_manager = job_manager
        self.port = port or self.DEFAULT_PORT
        self.server = None
        self.thread = None
        
        # Share job_manager with handler
        DashboardHandler.job_manager = job_manager
    
    def start(self):
        """Start the web server in a background daemon thread"""
        try:
            self.server = HTTPServer(('', self.port), DashboardHandler)
            self.thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True,
                name='DashboardThread'
            )
            self.thread.start()
            print(f"✓ Web dashboard: http://localhost:{self.port}")
        except OSError as e:
            print(f"✗ Failed to start dashboard on port {self.port}: {e}")
        except Exception as e:
            print(f"✗ Dashboard error: {e}")
    
    def stop(self):
        """Stop the web server gracefully"""
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass  # Ignore shutdown errors