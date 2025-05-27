# Instructions for 7 day collection are located within the k8s-queue-monitor folder

# Instructions to Run the Queue Time Statistics Collection Script(12hr collection)
This Python script collects and analyzes Kubernetes pod queue times. Here's how to run it:

## Prerequisites
• Python 3 installed
• Required Python packages: pandas, openpyxl (for Excel output)
• Access to a Kubernetes cluster with kubectl configured
• Sufficient permissions to read pod information across namespaces

## Installation Steps
1. Save the script as queue_stats_collector.py
2. Make it executable:  
  
chmod +x queue_stats_collector.py  
3. Install required dependencies:  
  
pip install pandas openpyxl  
## Running the Script
### Basic Usage
./queue_stats_collector.py

This will run with default settings:
• 5 minutes collection duration
• 60 seconds interval between collections
• Excludes kube-system namespace
• Uses hardcoded kubeconfig at /root/.kube/config
• Update to your Kubeconfig path in the code
### Custom Duration and Interval
./queue_stats_collector.py [duration_minutes] [interval_seconds]

Example:
./queue_stats_collector.py 10 30

Run for 720MIN (12HRS) every 5 min
./queue_stats_collector.py 720 300

For 12hrs collection
nohup ./queue_stats_collector.py 5 300 > queue_stats.log 2>&1 &
nohup ./queue_stats_collector.py 720 300 > queue_stats.log 2>&1 &

This will run for 10 minutes, collecting data every 30 seconds.
## Output
The script creates a timestamped directory (queue_stats_YYYYMMDD_HHMMSS) containing:
• all_queue_times.csv/.xlsx: Raw data for all pods
• namespace_stats.csv/.xlsx: Statistics grouped by namespace
• top_pods.csv/.xlsx: Details on pods with longest queue times
• queue_time_summary.xlsx: Summary report with overall statistics
## Notes
• The script ignores pods with unreasonable queue times (>30 days)
• It uses a hardcoded kubeconfig path at /root/.kube/config
• It will unset any existing KUBECONFIG environment variable
