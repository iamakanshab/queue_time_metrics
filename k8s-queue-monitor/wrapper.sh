#!/bin/bash
# K8s Queue Monitor Wrapper Script
cd "$(dirname "$0")"

export K8S_QUEUE_MONITOR_KUBECTL_PATH="/usr/local/bin/kubectl"
export K8S_QUEUE_MONITOR_KUBECONFIG="/home/USERNAME/.kube/config"
export K8S_QUEUE_MONITOR_OUTPUT_DIR="/home/USERNAME/k8s-queue-monitor-data"

# Create logs directory if it doesn't exist
mkdir -p logs

# Run collector with logging
python3 queue_time_collector.py >> logs/monitor.log 2>&1
