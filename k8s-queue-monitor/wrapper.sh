#!/bin/bash
# K8s Queue Monitor Wrapper Script
cd "$(dirname "$0")"

# Create logs directory if it doesn't exist
mkdir -p logs

# Run collector with logging
python3 queue_time_collector.py >> logs/monitor.log 2>&1
