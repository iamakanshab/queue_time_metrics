#!/usr/bin/env python3
import subprocess
import json
import pandas as pd
import time
import os
import datetime
from pathlib import Path
import sys

class QueueTimeCollector:
    def __init__(self, output_dir=None, exclude_namespaces=None):
        """Initialize the collector with configurable parameters"""
        self.exclude_namespaces = exclude_namespaces or ['kube-system']

        # Get paths from environment variables or use defaults
        self.kubeconfig = os.environ.get('K8S_QUEUE_MONITOR_KUBECONFIG', 
                                        os.path.expanduser("~/.kube/config"))
        self.kubectl_path = os.environ.get('K8S_QUEUE_MONITOR_KUBECTL_PATH', 
                                          "/usr/local/bin/kubectl")
        
        # Output directory - configurable via env var or parameter
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = os.environ.get('K8S_QUEUE_MONITOR_OUTPUT_DIR', 
                                            os.path.expanduser("~/k8s-queue-monitor-data"))

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

        # Path for persistent data
        self.persistent_db_path = os.path.join(self.output_dir, "queue_time_history.csv")

        # Load existing data or create new dataframe
        if os.path.exists(self.persistent_db_path):
            self.historical_data = pd.read_csv(self.persistent_db_path)
            print(f"Loaded {len(self.historical_data)} historical queue time records")
        else:
            self.historical_data = pd.DataFrame(columns=[
                'Timestamp', 'Namespace', 'Pod', 'PodUID', 'QueueTime',
                'CreationTime', 'StartTime'
            ])
            print("Created new persistent queue time database")

    def format_time(self, seconds):
        """Format seconds into days, hours, minutes, seconds"""
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(days)}d {int(hours)}h {int(minutes)}m {round(seconds, 2)}s"

    def collect_queue_times(self):
        """Collect current queue times from the cluster"""
        try:
            # Run kubectl command
            kubectl_cmd = [self.kubectl_path, f"--kubeconfig={self.kubeconfig}", 
                          "get", "pods", "--all-namespaces", "-o", "json"]
            result = subprocess.run(kubectl_cmd, capture_output=True, text=True, check=True)

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
                    pod_uid = pod['metadata']['uid']

                    # Parse timestamps
                    created_time = pd.to_datetime(pod['metadata']['creationTimestamp'])
                    start_time = pd.to_datetime(pod['status']['startTime'])

                    # Calculate queue time in seconds
                    queue_time = (start_time - created_time).total_seconds()

                    # Skip unreasonable queue times
                    if queue_time > 30 * 24 * 60 * 60:
                        continue

                    queue_times.append({
                        'Timestamp': timestamp,
                        'Namespace': namespace,
                        'Pod': pod_name,
                        'PodUID': pod_uid,
                        'QueueTime': queue_time,
                        'CreationTime': pod['metadata']['creationTimestamp'],
                        'StartTime': pod['status']['startTime']
                    })

            return pd.DataFrame(queue_times)

        except Exception as e:
            print(f"Error collecting queue times: {str(e)}")
            return pd.DataFrame()

    def update_persistent_storage(self, new_data):
        """Update persistent storage with new data and maintain 7-day window"""
        if not new_data.empty:
            # Add new data
            self.historical_data = pd.concat([self.historical_data, new_data], ignore_index=True)

            # Keep only last 7 days of data
            self.historical_data['Timestamp'] = pd.to_datetime(self.historical_data['Timestamp'])
            cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=7)
            self.historical_data = self.historical_data[self.historical_data['Timestamp'] >= cutoff_date]

            # Convert back to string for storage
            self.historical_data['Timestamp'] = self.historical_data['Timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")

            # Save to disk
            self.historical_data.to_csv(self.persistent_db_path, index=False)
            print(f"Updated persistent storage with {len(new_data)} new records")
            print(f"Total records in 7-day window: {len(self.historical_data)}")

    def run_collection(self):
        """Run a single collection cycle"""
        print(f"Starting collection at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Collect data
        new_data = self.collect_queue_times()

        if not new_data.empty:
            # Update storage
            self.update_persistent_storage(new_data)
            print("Collection completed successfully")
        else:
            print("No data collected in this run")

        print(f"Data stored in: {self.persistent_db_path}")

# Main execution
if __name__ == "__main__":
    collector = QueueTimeCollector()
    collector.run_collection()
