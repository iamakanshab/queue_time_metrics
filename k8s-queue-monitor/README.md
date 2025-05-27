# K8s Queue Monitor

Automatically monitor Kubernetes pod queue times with 7-day historical tracking.

## What it does

- Collects pod queue times every 15 minutes via cron job
- Maintains 7 days of historical data in a rolling window
- Generates comprehensive reports by namespace and daily trends

## Quick Setup

### 1. Download and Install

```bash
# Git clone the repository
git clone https://github.com/iamakanshab/queue_time_metrics.git

# Change directory to k8s-queue-monitor
cd k8s-queue-monitor

# Install Python dependencies
pip3 install -r requirements.txt
```
### Environment Variables 

```bash
export K8S_QUEUE_MONITOR_OUTPUT_DIR=/your/data/path
export K8S_QUEUE_MONITOR_KUBECONFIG=/your/kubeconfig/path
export K8S_QUEUE_MONITOR_KUBECTL_PATH=/usr/local/bin/kubectl
```

### Default Locations

- **Data**: `~/k8s-queue-monitor-data/`
- **Kubeconfig**: `~/.kube/config`
- **kubectl**: `/usr/local/bin/kubectl`
- **Logs**: `./logs/monitor.log`


### 2. Test Collection 

```bash
# Test that everything works
python3 queue_time_collector.py
```

### 3. Setup Automated Collection

```bash
# Method 1: Import crontab file 
sed -i "s|/home/USERNAME|$HOME|g" k8s-monitor.crontab
crontab k8s-monitor.crontab

# Method 2: Manual setup
crontab -e
# Add: */15 * * * * /full/path/to/k8s-queue-monitor/wrapper.sh
eg:
*/15 * * * * /home/akbansal/k8s-queue-monitor/wrapper.sh
```

### 4. Verify Setup

```bash
# Check cron job was added
crontab -l | grep k8s

# Wait 30+ minutes, then check logs ( the logs folder is created after running the wrapper.sh script)
tail -f logs/monitor.log
```

### 5. Generate Reports

```bash
# After data has been collected (30+ minutes) -first time setup only
python3 process_logs.py

# After 7 days
python3 -m venv venv
source venv/bin/activate
pip install pandas
python3 process_logs.py
```

## Configuration


## Files Structure

```
k8s-queue-monitor/
├── queue_time_collector.py   # Main collector script
├── process_logs.py           # Report generator
├── wrapper.sh               # Cron wrapper script
├── k8s-monitor.crontab      # Crontab file for import
├── requirements.txt         # Python dependencies
├── logs/                   # Created automatically
│   └── monitor.log         # Collection logs and errors
└── README.md               # This file
```

## Output Files

**Data Directory** (`~/k8s-queue-monitor-data/` by default):
- `queue_time_history.csv` - Raw collected data (7-day rolling window)
- `reports/namespace_stats_TIMESTAMP.csv` - Per-namespace statistics
- `reports/deduplicated_data_TIMESTAMP.csv` - Processed data for analysis

## Commands Reference

```bash
# Collect queue times once (for testing)
python3 queue_time_collector.py

# Process logs and generate reports
python3 process_logs.py

# Process specific data file
python3 process_logs.py /path/to/specific/file.csv

# Check cron job status
crontab -l | grep k8s

# View collection logs
tail -f logs/monitor.log

# Check data directory
ls -la ~/k8s-queue-monitor-data/
```

## Troubleshooting

### No data after 30+ minutes?

```bash
# Check if kubectl works
kubectl get pods --all-namespaces

# Check cron job exists
crontab -l | grep k8s

# Check logs for errors
tail -20 logs/monitor.log

# Test collection manually
python3 queue_time_collector.py
```

### Permission issues?

```bash
# Fix kubeconfig permissions
chmod 600 ~/.kube/config

# Make wrapper script executable
chmod +x wrapper.sh

# Check script paths in crontab
crontab -l
```

### Collection errors?

```bash
# Check kubectl path
which kubectl

# Test kubectl with your kubeconfig
kubectl --kubeconfig ~/.kube/config get pods --all-namespaces

# Check if pandas is installed
python3 -c "import pandas; print('pandas OK')"
```

### Want to change data location?

```bash
# Set environment variable
export K8S_QUEUE_MONITOR_OUTPUT_DIR=/new/path

# Update crontab to use the environment variable
crontab -e
# Modify the line to: */15 * * * * /path/to/wrapper.sh
```

### Cron job not running?

```bash
# Check cron service
sudo systemctl status cron

# Check system cron logs
grep CRON /var/log/syslog | tail -10

# Test wrapper script manually
./wrapper.sh
```

## Data Retention

- **Collection**: Every 15 minutes
- **History**: 7-day rolling window (older data automatically removed)
- **Reports**: Saved with timestamps (not automatically removed)
- **Logs**: Persistent (rotate manually if needed)

## Customization

### Change collection interval

1. Edit `k8s-monitor.crontab`
2. Change `*/15` to your preferred interval (e.g., `*/30` for 30 minutes)
3. Re-import: `crontab k8s-monitor.crontab`

### Exclude additional namespaces

Edit `queue_time_collector.py` and modify:
```python
self.exclude_namespaces = exclude_namespaces or ['kube-system', 'your-namespace']
```

### Change data retention period

Edit `queue_time_collector.py` and modify:
```python
cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=14)  # 14 days instead of 7
```
