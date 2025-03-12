#!/usr/bin/env python3
import os
import subprocess
import json
import pandas as pd
import time
import datetime
from pathlib import Path
import sys
import threading
import flask
from flask import Flask, render_template, request, send_from_directory, jsonify, redirect, url_for, Response
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['UPLOAD_FOLDER'] = 'reports'
app.config['SECRET_KEY'] = str(uuid.uuid4())

# Create necessary directories
os.makedirs('reports', exist_ok=True)
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)

# Global variables to track collection status
collection_status = {
    'active': False,
    'current_run': None,
    'recent_runs': [],
    'max_recent_runs': 10
}

class QueueTimeStatsCollector:
    def __init__(self, duration_mins=5, interval_secs=60, output_dir=None, exclude_namespaces=None, kubeconfig=None):
        """
        Initialize the collector
        
        Args:
            duration_mins: Collection duration in minutes (default: 5)
            interval_secs: Interval between collections in seconds (default: 60)
            output_dir: Directory to store results (default: auto-generated)
            exclude_namespaces: List of namespaces to exclude (default: ['kube-system'])
            kubeconfig: Path to kubeconfig file (default: None, will use hardcoded path)
        """
        self.duration_mins = duration_mins
        self.interval_secs = interval_secs
        self.exclude_namespaces = exclude_namespaces or ['kube-system']
        
        # Hardcode the kubeconfig path to /root/.kube/config
        self.kubeconfig = kubeconfig or "/root/.kube/config"
        
        # Verify kubeconfig exists
        if not os.path.exists(self.kubeconfig):
            logger.warning(f"WARNING: Kubeconfig file not found at {self.kubeconfig}")
        else:
            logger.info(f"Using kubeconfig: {self.kubeconfig}")
        
        # Create timestamp for output directory
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = output_dir or os.path.join("reports", f"queue_stats_{timestamp}")
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize DataFrame to store all collected data
        self.all_data = pd.DataFrame(columns=['Timestamp', 'Namespace', 'Pod', 'QueueTime', 'QueueTimeFormatted', 
                                              'Days', 'Hours', 'Minutes', 'Seconds'])
        
        # Collection logs
        self.logs = []
        self.log(f"Starting queue time statistics collection for {duration_mins} minutes.")
        self.log(f"Excluding namespaces: {', '.join(self.exclude_namespaces)}")
        self.log(f"Data will be saved to {self.output_dir}/")
    
    def log(self, message):
        """Add a log message and print it"""
        logger.info(message)
        self.logs.append(message)
        return message
    
    def format_time_components(self, seconds):
        """Convert seconds to days, hours, minutes, seconds format"""
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        return {
            'Days': int(days),
            'Hours': int(hours),
            'Minutes': int(minutes),
            'Seconds': round(seconds, 2),
            'Formatted': f"{int(days)}d {int(hours)}h {int(minutes)}m {round(seconds, 2)}s"
        }
    
    def collect_queue_times(self):
        """Run kubectl command and collect queue times for all namespaces (except excluded ones)"""
        try:
            # Build kubectl command with properly expanded kubeconfig path
            kubectl_cmd = ["kubectl", f"--kubeconfig={self.kubeconfig}", "get", "pods", "--all-namespaces", "-o", "json"]
            
            # Print the command for debugging
            self.log(f"Running command: {' '.join(kubectl_cmd)}")
            
            # Run kubectl command
            result = subprocess.run(
                kubectl_cmd,
                capture_output=True, text=True, check=True
            )
            
            # Parse JSON output
            pods_data = json.loads(result.stdout)
            
            # Process pod data
            queue_times = []
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for pod in pods_data['items']:
                namespace = pod['metadata']['namespace']
                
                # Skip excluded namespaces
                if namespace in self.exclude_namespaces:
                    continue
                    
                if pod.get('status', {}).get('startTime'):
                    pod_name = pod['metadata']['name']
                    
                    # Parse timestamps
                    created_time = pd.to_datetime(pod['metadata']['creationTimestamp'])
                    start_time = pd.to_datetime(pod['status']['startTime'])
                    
                    # Calculate queue time in seconds
                    queue_time = (start_time - created_time).total_seconds()
                    
                    # Skip unreasonable queue times (more than 30 days)
                    if queue_time > 30 * 24 * 60 * 60:
                        self.log(f"Skipping pod {namespace}/{pod_name} with unreasonable queue time: {queue_time:.2f} seconds")
                        continue
                    
                    # Format queue time into components
                    time_components = self.format_time_components(queue_time)
                    
                    queue_times.append({
                        'Timestamp': timestamp,
                        'Namespace': namespace,
                        'Pod': pod_name,
                        'QueueTime': queue_time,
                        'QueueTimeFormatted': time_components['Formatted'],
                        'Days': time_components['Days'],
                        'Hours': time_components['Hours'],
                        'Minutes': time_components['Minutes'],
                        'Seconds': time_components['Seconds'],
                        'CreationTime': pod['metadata']['creationTimestamp'],
                        'StartTime': pod['status']['startTime']
                    })
            
            return pd.DataFrame(queue_times)
            
        except subprocess.CalledProcessError as e:
            self.log(f"Error running kubectl command: {e}")
            self.log(f"Command output: {e.stderr}")
            return pd.DataFrame()
        except json.JSONDecodeError as e:
            self.log(f"Error parsing JSON output: {e}")
            return pd.DataFrame()
        except Exception as e:
            self.log(f"Unexpected error: {str(e)}")
            return pd.DataFrame()
    
    def run_collection(self):
        """Collect data at regular intervals for the specified duration"""
        # Calculate number of iterations
        iterations = int(self.duration_mins * 60 / self.interval_secs)
        
        for i in range(1, iterations + 1):
            self.log(f"[{i}/{iterations}] Collecting data...")
            
            # Collect data
            df = self.collect_queue_times()
            
            if not df.empty:
                # Add to overall dataset
                self.all_data = pd.concat([self.all_data, df], ignore_index=True)
                
                # Print current stats
                self.log(f"Collected data for {len(df)} pods across {df['Namespace'].nunique()} namespaces")
                
                # Calculate and print overall stats for this iteration
                avg_queue = df['QueueTime'].mean()
                max_queue = df['QueueTime'].max()
                max_ns = df.loc[df['QueueTime'].idxmax(), 'Namespace'] if not df.empty else "N/A"
                max_pod = df.loc[df['QueueTime'].idxmax(), 'Pod'] if not df.empty else "N/A"
                
                # Format times for display
                avg_formatted = self.format_time_components(avg_queue)['Formatted']
                max_formatted = self.format_time_components(max_queue)['Formatted']
                
                self.log(f"Average queue time: {avg_formatted} ({avg_queue:.2f} seconds)")
                self.log(f"Maximum queue time: {max_formatted} ({max_queue:.2f} seconds) in {max_ns}/{max_pod}")
            else:
                self.log("No data collected in this iteration")
            
            # Wait for next interval if not the last iteration
            if i < iterations:
                self.log(f"Waiting {self.interval_secs} seconds until next collection...")
                time.sleep(self.interval_secs)
    
    def generate_statistics(self):
        """Generate and print statistics from collected data and create comprehensive Excel report"""
        if self.all_data.empty:
            self.log("No data collected, cannot generate statistics.")
            return
        
        # Save raw data to CSV
        self.all_data.to_csv(os.path.join(self.output_dir, "all_queue_times.csv"), index=False)
        
        # Calculate overall statistics
        self.log("\n=== OVERALL QUEUE TIME STATISTICS ===")
        total_pods = len(self.all_data['Pod'].unique())
        total_namespaces = len(self.all_data['Namespace'].unique())
        overall_avg = self.all_data['QueueTime'].mean()
        overall_max = self.all_data['QueueTime'].max()
        max_ns = self.all_data.loc[self.all_data['QueueTime'].idxmax(), 'Namespace'] if not self.all_data.empty else "N/A"
        max_pod = self.all_data.loc[self.all_data['QueueTime'].idxmax(), 'Pod'] if not self.all_data.empty else "N/A"
        
        # Format times for display
        avg_formatted = self.format_time_components(overall_avg)['Formatted']
        max_formatted = self.format_time_components(overall_max)['Formatted']
        
        self.log(f"Total unique pods: {total_pods}")
        self.log(f"Total namespaces: {total_namespaces}")
        self.log(f"Overall average queue time: {avg_formatted} ({overall_avg:.2f} seconds)")
        self.log(f"Overall maximum queue time: {max_formatted} ({overall_max:.2f} seconds) in {max_ns}/{max_pod}")
        
        # Create a function to calculate formatted times for agg operations
        def format_time(seconds):
            return self.format_time_components(seconds)['Formatted']
        
        # Group by namespace and calculate stats
        ns_stats = self.all_data.groupby('Namespace').agg(
            PodCount=('Pod', 'nunique'),
            AvgQueueTime=('QueueTime', 'mean'),
            MaxQueueTime=('QueueTime', 'max'),
            MinQueueTime=('QueueTime', 'min'),
            StdQueueTime=('QueueTime', 'std')
        ).reset_index()
        
        # Add formatted time columns
        ns_stats['AvgQueueTimeFormatted'] = ns_stats['AvgQueueTime'].apply(format_time)
        ns_stats['MaxQueueTimeFormatted'] = ns_stats['MaxQueueTime'].apply(format_time)
        ns_stats['MinQueueTimeFormatted'] = ns_stats['MinQueueTime'].apply(format_time)
        
        # Create component columns for Excel
        for stat in ['AvgQueueTime', 'MaxQueueTime', 'MinQueueTime']:
            ns_stats[f'{stat}Days'] = ns_stats[stat].apply(lambda x: self.format_time_components(x)['Days'])
            ns_stats[f'{stat}Hours'] = ns_stats[stat].apply(lambda x: self.format_time_components(x)['Hours'])
            ns_stats[f'{stat}Minutes'] = ns_stats[stat].apply(lambda x: self.format_time_components(x)['Minutes'])
            ns_stats[f'{stat}Seconds'] = ns_stats[stat].apply(lambda x: self.format_time_components(x)['Seconds'])
        
        # Sort by average queue time (descending)
        ns_stats = ns_stats.sort_values('AvgQueueTime', ascending=False)
        
        # Print namespace statistics
        self.log("\n=== QUEUE TIME STATISTICS BY NAMESPACE ===")
        display_cols = ['Namespace', 'PodCount', 'AvgQueueTimeFormatted', 'MaxQueueTimeFormatted', 'MinQueueTimeFormatted']
        ns_display = ns_stats[display_cols].to_string(index=False)
        self.log(ns_display)
        
        # Save namespace statistics to CSV
        ns_stats.to_csv(os.path.join(self.output_dir, "namespace_stats.csv"), index=False)
        
        # Identify top pods with longest queue times
        self.log("\n=== TOP 10 PODS WITH LONGEST QUEUE TIMES ===")
        top_pods = self.all_data.sort_values('QueueTime', ascending=False).drop_duplicates(['Namespace', 'Pod']).head(10)
        
        # Display with formatted time
        top_pods_display = top_pods[['Namespace', 'Pod', 'QueueTimeFormatted', 'CreationTime', 'StartTime']].copy()
        top_pods_string = top_pods_display.to_string(index=False)
        self.log(top_pods_string)
        
        # Save top pods data to CSV
        top_pods.to_csv(os.path.join(self.output_dir, "top_pods.csv"), index=False)
        
        # Generate text statistics report file
        report_file = os.path.join(self.output_dir, "queue_stats_report.txt")
        with open(report_file, 'w') as f:
            f.write("=== KUBERNETES POD QUEUE TIME STATISTICS ===\n\n")
            f.write(f"Report generated: {datetime.datetime.now()}\n")
            f.write(f"Collection period: {self.duration_mins} minutes\n")
            f.write(f"Collection interval: {self.interval_secs} seconds\n")
            f.write(f"Excluded namespaces: {', '.join(self.exclude_namespaces)}\n\n")
            
            f.write("=== OVERALL STATISTICS ===\n")
            f.write(f"Total unique pods: {total_pods}\n")
            f.write(f"Total namespaces: {total_namespaces}\n")
            f.write(f"Overall average queue time: {avg_formatted} ({overall_avg:.2f} seconds)\n")
            f.write(f"Overall maximum queue time: {max_formatted} ({overall_max:.2f} seconds) in {max_ns}/{max_pod}\n\n")
            
            f.write("=== STATISTICS BY NAMESPACE ===\n")
            f.write("Namespace, PodCount, AvgQueueTime, AvgQueueTimeFormatted, MaxQueueTime, MaxQueueTimeFormatted, MinQueueTime, MinQueueTimeFormatted\n")
            for _, row in ns_stats.iterrows():
                f.write(f"{row['Namespace']}, {row['PodCount']}, {row['AvgQueueTime']:.2f}, {row['AvgQueueTimeFormatted']}, ")
                f.write(f"{row['MaxQueueTime']:.2f}, {row['MaxQueueTimeFormatted']}, {row['MinQueueTime']:.2f}, {row['MinQueueTimeFormatted']}\n")
            
            f.write("\n=== TOP 10 PODS WITH LONGEST QUEUE TIMES ===\n")
            f.write("Namespace, Pod, QueueTime, QueueTimeFormatted, CreationTime, StartTime\n")
            for _, row in top_pods.iterrows():
                f.write(f"{row['Namespace']}, {row['Pod']}, {row['QueueTime']:.2f}, {row['QueueTimeFormatted']}, ")
                f.write(f"{row['CreationTime']}, {row['StartTime']}\n")
        
        self.log(f"Detailed statistics report saved to: {report_file}")
        
        # Generate a single comprehensive Excel report with multiple sheets
        excel_report_path = os.path.join(self.output_dir, "kubernetes_queue_time_report.xlsx")
        
        try:
            # Create ExcelWriter object with openpyxl engine
            with pd.ExcelWriter(excel_report_path, engine='openpyxl') as writer:
                # Create summary sheet
                summary_data = {
                    'Metric': [
                        'Report Generated',
                        'Collection Period (minutes)',
                        'Collection Interval (seconds)',
                        'Total Unique Pods',
                        'Total Namespaces',
                        'Overall Average Queue Time',
                        'Overall Average Queue Time (seconds)',
                        'Overall Maximum Queue Time',
                        'Overall Maximum Queue Time (seconds)',
                        'Pod with Maximum Queue Time',
                        'Excluded Namespaces'
                    ],
                    'Value': [
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        self.duration_mins,
                        self.interval_secs,
                        total_pods,
                        total_namespaces,
                        avg_formatted,
                        f"{overall_avg:.2f}",
                        max_formatted,
                        f"{overall_max:.2f}",
                        f"{max_ns}/{max_pod}",
                        ', '.join(self.exclude_namespaces)
                    ]
                }
                
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Make the summary sheet more readable
                workbook = writer.book
                worksheet = writer.sheets['Summary']
                
                # Adjust column widths
                worksheet.column_dimensions['A'].width = 35
                worksheet.column_dimensions['B'].width = 50
                
                # Add namespace statistics sheet
                display_order = ['Namespace', 'PodCount', 
                                'AvgQueueTime', 'AvgQueueTimeFormatted', 'AvgQueueTimeDays', 'AvgQueueTimeHours', 'AvgQueueTimeMinutes', 'AvgQueueTimeSeconds',
                                'MaxQueueTime', 'MaxQueueTimeFormatted', 'MaxQueueTimeDays', 'MaxQueueTimeHours', 'MaxQueueTimeMinutes', 'MaxQueueTimeSeconds',
                                'MinQueueTime', 'MinQueueTimeFormatted', 'MinQueueTimeDays', 'MinQueueTimeHours', 'MinQueueTimeMinutes', 'MinQueueTimeSeconds',
                                'StdQueueTime']
                
                ns_stats_display = ns_stats[display_order]
                ns_stats_display.to_excel(writer, sheet_name='Namespace Statistics', index=False)
                
                # Format the namespace statistics sheet
                worksheet = writer.sheets['Namespace Statistics']
                worksheet.column_dimensions['A'].width = 25  # Namespace
                
                # Add top pods sheet
                top_pods.to_excel(writer, sheet_name='Top 10 Longest Queue Times', index=False)
                
                # Add all data sheet
                self.all_data.to_excel(writer, sheet_name='All Queue Time Data', index=False)
                
                # Add pivot tables sheet
                # Create pivot table data for namespaces
                pivot_data = self.all_data.pivot_table(
                    values='QueueTime',
                    index=['Namespace'],
                    aggfunc={
                        'QueueTime': ['count', 'mean', 'min', 'max', 'std']
                    }
                ).reset_index()
                
                # Flatten the column hierarchy
                pivot_data.columns = ['Namespace', 'Count', 'Average', 'Minimum', 'Maximum', 'StdDev']
                
                # Add formatted columns
                pivot_data['Average Formatted'] = pivot_data['Average'].apply(format_time)
                pivot_data['Minimum Formatted'] = pivot_data['Minimum'].apply(format_time)
                pivot_data['Maximum Formatted'] = pivot_data['Maximum'].apply(format_time)
                
                # Sort by average queue time
                pivot_data = pivot_data.sort_values('Average', ascending=False)
                
                # Write to Excel
                pivot_data.to_excel(writer, sheet_name='Pivot Analysis', index=False)
                
            self.log(f"Comprehensive Excel report saved to: {excel_report_path}")
            return excel_report_path
            
        except Exception as e:
            self.log(f"Error creating Excel report: {str(e)}")
            self.log("Falling back to individual CSV files..")
            # Save individual Excel files as fallback
            self.all_data.to_excel(os.path.join(self.output_dir, "all_queue_times.xlsx"), index=False, engine='openpyxl')
            ns_stats.to_excel(os.path.join(self.output_dir, "namespace_stats.xlsx"), index=False, engine='openpyxl')
            top_pods.to_excel(os.path.join(self.output_dir, "top_pods.xlsx"), index=False, engine='openpyxl')
            return os.path.join(self.output_dir, "all_queue_times.xlsx")
    
    def run(self):
        """Run the entire collection and analysis process"""
        self.run_collection()
        excel_path = self.generate_statistics()
        self.log("Collection and analysis complete!")
        return {
            'output_dir': self.output_dir,
            'excel_path': excel_path,
            'logs': self.logs
        }


def start_collection(duration, interval, excluded_namespaces=None, kubeconfig=None):
    """Start a new collection in a separate thread"""
    global collection_status
    
    if collection_status['active']:
        return {"error": "Collection already in progress"}
    
    # Set up collection parameters
    if not excluded_namespaces:
        excluded_namespaces = ['kube-system']
    
    # Generate a unique ID for this run
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("reports", f"queue_stats_{run_id}")
    
    # Create a collector
    collector = QueueTimeStatsCollector(
        duration_mins=duration, 
        interval_secs=interval,
        output_dir=output_dir,
        exclude_namespaces=excluded_namespaces,
        kubeconfig=kubeconfig
    )
    
    # Update status
    collection_status['active'] = True
    collection_status['current_run'] = {
        'id': run_id,
        'start_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'duration': duration,
        'interval': interval,
        'output_dir': output_dir,
        'logs': collector.logs,
        'status': 'running'
    }
    
    # Define the thread function
    def collection_thread():
        try:
            # Run the collector
            results = collector.run()
            
            # Update status
            collection_status['active'] = False
            
            # Update current run information
            collection_status['current_run'].update({
                'end_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'status': 'completed',
                'logs': results['logs'],
                'excel_path': results['excel_path'],
                'report_url': f"/reports/{os.path.basename(output_dir)}"
            })
            
            # Add to recent runs
            if collection_status['current_run']:
                collection_status['recent_runs'].insert(0, collection_status['current_run'])
                # Limit the number of recent runs stored
                if len(collection_status['recent_runs']) > collection_status['max_recent_runs']:
                    collection_status['recent_runs'] = collection_status['recent_runs'][:collection_status['max_recent_runs']]
            
            collection_status['current_run'] = None
            
        except Exception as e:
            logger.error(f"Error in collection thread: {str(e)}")
            collection_status['active'] = False
            if collection_status['current_run']:
                collection_status['current_run']['status'] = 'failed'
                collection_status['current_run']['error'] = str(e)
    
    # Start the collection thread
    thread = threading.Thread(target=collection_thread)
    thread.daemon = True
    thread.start()
    
    return {
        "success": True, 
        "message": f"Started collection with ID: {run_id}",
        "run_id": run_id
    }


# Create HTML template files
def create_template_files():
    # Create base template
    with open('templates/base.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Kubernetes Queue Time Monitor{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.1.1/css/all.min.css">
    <style>
        body {
            padding-top: 20px;
            background-color: #f8f9fa;
        }
        .card {
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .log-container {
            background-color: #212529;
            color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            max-height: 400px;
            overflow-y: auto;
            font-family: monospace;
        }
        .log-line {
            margin: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .navbar {
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .btn-action {
            margin-right: 10px;
        }
        .status-running {
            color: #007bff;
        }
        .status-completed {
            color: #28a745;
        }
        .status-failed {
            color: #dc3545;
        }
    </style>
    {% block extra_head %}{% endblock %}
</head>
<body>
    <div class="container">
        <nav class="navbar navbar-expand-lg navbar-dark bg-dark rounded">
            <div class="container-fluid">
                <a class="navbar-brand" href="/">
                    <i class="fas fa-tachometer-alt"></i> K8s Queue Monitor
                </a>
                <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                    <span class="navbar-toggler-icon"></span>
                </button>
                <div class="collapse navbar-collapse" id="navbarNav">
                    <ul class="navbar-nav">
                        <li class="nav-item">
                            <a class="nav-link {% if request.path == '/' %}active{% endif %}" href="/">
                                <i class="fas fa-home"></i> Home
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link {% if request.path == '/reports' %}active{% endif %}" href="/reports">
                                <i class="fas fa-file-alt"></i> Reports
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link {% if request.path == '/settings' %}active{% endif %}" href="/settings">
                                <i class="fas fa-cog"></i> Settings
                            </a>
                        </li>
                    </ul>
                </div>
            </div>
        </nav>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }} alert-dismissible fade show">
                {{ message }}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    {% block extra_scripts %}{% endblock %}
</body>
</html>
        ''')
    
    # Create home template
    with open('templates/index.html', 'w') as f:
        f.write('''
{% extends "base.html" %}

{% block title %}K8s Queue Monitor - Dashboard{% endblock %}

{% block extra_head %}
<meta http-equiv="refresh" content="30">
{% endblock %}

{% block content %}
<div class="row">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h5><i class="fas fa-play-circle"></i> Start Queue Time Collection</h5>
            </div>
            <div class="card-body">
                <form action="/start_collection" method="post" class="row g-3">
                    <div class="col-md-4">
                        <label for="duration" class="form-label">Duration (minutes)</label>
                        <input type="number" class="form-control" id="duration" name="duration" value="5" min="1" max="60" required>
                    </div>
                    <div class="col-md-4">
                        <label for="interval" class="form-label">
