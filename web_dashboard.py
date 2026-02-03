"""
Simple web dashboard for Taskmaster
Provides a web interface to view process status
Run on http://localhost:8080
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
from urllib.parse import urlparse, parse_qs


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the dashboard"""
    
    job_manager = None  # Will be set by WebDashboard
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            self.serve_html()
        elif parsed_path.path == '/api/status':
            self.serve_status_json()
        elif parsed_path.path == '/api/programs':
            self.serve_programs_json()
        else:
            self.send_error(404)
    
    def serve_html(self):
        """Serve the main HTML dashboard"""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Taskmaster Dashboard</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #4CAF50;
            color: white;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .status {
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
        }
        .running {
            background-color: #4CAF50;
            color: white;
        }
        .starting {
            background-color: #FFC107;
            color: white;
        }
        .stopped {
            background-color: #9E9E9E;
            color: white;
        }
        .exited {
            background-color: #f44336;
            color: white;
        }
        .refresh-btn {
            background-color: #2196F3;
            color: white;
            border: none;
            padding: 10px 20px;
            cursor: pointer;
            border-radius: 4px;
            font-size: 16px;
        }
        .refresh-btn:hover {
            background-color: #0b7dda;
        }
        .last-update {
            color: #666;
            font-size: 14px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Taskmaster Dashboard</h1>
        <button class="refresh-btn" onclick="loadStatus()">Refresh</button>
        <div class="last-update" id="lastUpdate"></div>
        <table id="statusTable">
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
                    <td colspan="6" style="text-align: center;">Loading...</td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <script>
        function loadStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    updateTable(data);
                    document.getElementById('lastUpdate').textContent = 
                        'Last updated: ' + new Date().toLocaleTimeString();
                })
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('statusBody').innerHTML = 
                        '<tr><td colspan="6" style="text-align: center; color: red;">Error loading status</td></tr>';
                });
        }
        
        function updateTable(programs) {
            const tbody = document.getElementById('statusBody');
            
            if (programs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">No programs running</td></tr>';
                return;
            }
            
            tbody.innerHTML = programs.map(prog => `
                <tr>
                    <td>${prog.name}</td>
                    <td>${prog.instance}</td>
                    <td><span class="status ${prog.status.toLowerCase()}">${prog.status}</span></td>
                    <td>${prog.pid || '-'}</td>
                    <td>${prog.uptime}s</td>
                    <td>${prog.retries}</td>
                </tr>
            `).join('');
        }
        
        // Auto-refresh every 5 seconds
        setInterval(loadStatus, 5000);
        
        // Initial load
        loadStatus();
    </script>
</body>
</html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        try:
            self.safe_write(html.encode())
        except Exception:
            pass
    
    def serve_status_json(self):
        """Serve status as JSON"""
        if not self.job_manager:
            self.send_error(500)
            return
        
        status_list = []
        # Include all configured programs, even if they have no running instances
        programs = sorted(set(list(self.job_manager.config.keys()) + list(self.job_manager.jobs.keys())))

        with self.job_manager.lock:
            for name in programs:
                proc_infos = self.job_manager.jobs.get(name)

                # If no processes for this program, report a single STOPPED entry
                if not proc_infos:
                    status_list.append({
                        'name': name,
                        'instance': '-',
                        'status': 'STOPPED',
                        'pid': None,
                        'uptime': 0,
                        'retries': 0
                    })
                    continue

                for i, proc_info in enumerate(proc_infos):
                    uptime = int(time.time() - proc_info.start_time) if proc_info.process.poll() is None else 0

                    if proc_info.process.poll() is None:
                        status = "RUNNING" if proc_info.successfully_started else "STARTING"
                        pid = proc_info.process.pid
                    else:
                        status = "STOPPED"
                        pid = None

                    status_list.append({
                        'name': name,
                        'instance': i,
                        'status': status,
                        'pid': pid,
                        'uptime': uptime,
                        'retries': proc_info.retry_count
                    })
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        try:
            self.safe_write(json.dumps(status_list).encode())
        except Exception:
            pass
    
    def serve_programs_json(self):
        """Serve list of configured programs"""
        if not self.job_manager:
            self.send_error(500)
            return
        
        programs = list(self.job_manager.config.keys())
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        try:
            self.safe_write(json.dumps({'programs': programs}).encode())
        except Exception:
            pass
    
    def log_message(self, format, *args):
        """Suppress request logging"""
        pass

    def safe_write(self, data: bytes):
        """Write to the client socket but ignore BrokenPipe/ConnectionReset errors."""
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # Client closed connection; ignore
            pass


class WebDashboard:
    """Web dashboard server"""
    
    def __init__(self, job_manager, port=8080):
        self.job_manager = job_manager
        self.port = port
        self.server = None
        self.thread = None
        
        # Set the job_manager for the handler
        DashboardHandler.job_manager = job_manager
    
    def start(self):
        """Start the web server in a background thread"""
        try:
            self.server = HTTPServer(('', self.port), DashboardHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"Web dashboard started at http://localhost:{self.port}")
        except Exception as e:
            print(f"Failed to start web dashboard: {e}")
    
    def stop(self):
        """Stop the web server"""
        if self.server:
            self.server.shutdown()
            print("Web dashboard stopped")


# Import time for uptime calculation
import time