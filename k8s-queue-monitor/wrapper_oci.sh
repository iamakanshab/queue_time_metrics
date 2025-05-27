#!/bin/bash

# Log file location
LOG_FILE="/home/akbansal/monitor/monitor.log"

echo "====== Starting job at $(date) ======" >> $LOG_FILE

# Set environment variables for kubectl and OCI
export HOME=/home/akbansal
export PATH=/home/akbansal/lib/oracle-cli/bin:/home/akbansal/.local/bin:/home/akbansal/bin:/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin

# Log environment for debugging
echo "Running with PATH=$PATH" >> $LOG_FILE
echo "Running as user $(whoami)" >> $LOG_FILE

# Change to script directory
cd /home/akbansal/k8s-queue-monitor

# Run the Python script
/home/akbansal/gpu-metrics/venv/bin/python /home/akbansal/k8s-queue-monitor/queue_time_7days.py >> $LOG_FILE 2>&1

echo "====== Job completed at $(date) ======" >> $LOG_FILE
