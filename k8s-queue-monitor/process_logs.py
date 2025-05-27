#!/usr/bin/env python3
import pandas as pd
import os
import datetime
import sys

def format_time(seconds):
    """Format seconds into hours, minutes, seconds"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}h {int(minutes)}m {round(seconds, 2)}s"

def main():
    # Get input file from command line argument or environment variable
    if len(sys.argv) > 1:
        raw_logs_path = sys.argv[1]
    else:
        # Use environment variable or default path
        output_dir = os.environ.get('K8S_QUEUE_MONITOR_OUTPUT_DIR', 
                                   os.path.expanduser("~/k8s-queue-monitor-data"))
        raw_logs_path = os.path.join(output_dir, "queue_time_history.csv")

    # Check if input file exists
    if not os.path.exists(raw_logs_path):
        print(f"Error: Input file not found: {raw_logs_path}")
        print("Make sure to run the collector first or specify the correct file path")
        sys.exit(1)

    # Output directory for reports
    output_dir = os.path.join(os.path.dirname(raw_logs_path), "reports")
    os.makedirs(output_dir, exist_ok=True)

    # Load the raw data
    print(f"Loading data from: {raw_logs_path}")
    raw_data = pd.read_csv(raw_logs_path)

    # Check if data was loaded successfully
    if raw_data.empty:
        print("No data found in the raw logs")
        sys.exit(1)

    print(f"Number of records in raw data: {len(raw_data)}")

    # Ensure timestamp is proper datetime
    raw_data['Timestamp'] = pd.to_datetime(raw_data['Timestamp'])

    # Deduplicate by keeping only the first occurrence of each pod
    dedup_data = raw_data.sort_values('Timestamp').drop_duplicates(subset=['PodUID'])

    # Calculate overall statistics
    true_avg_queue_time = dedup_data['QueueTime'].mean()
    max_queue_time = dedup_data['QueueTime'].max()
    min_queue_time = dedup_data['QueueTime'].min()
    median_queue_time = dedup_data['QueueTime'].median()

    print("\n" + "="*70)
    print("7-DAY KUBERNETES QUEUE TIME ANALYSIS")
    print("="*70)
    print(f"Total unique pods: {len(dedup_data):,}")
    print(f"7-day average queue time: {format_time(true_avg_queue_time)} ({true_avg_queue_time:.2f}s)")
    print(f"Maximum queue time: {format_time(max_queue_time)} ({max_queue_time:.2f}s)")
    print(f"Minimum queue time: {format_time(min_queue_time)} ({min_queue_time:.2f}s)")
    print(f"Median queue time: {format_time(median_queue_time)} ({median_queue_time:.2f}s)")

    # Create namespace statistics
    ns_stats = dedup_data.groupby('Namespace').agg({
        'QueueTime': ['mean', 'max', 'count']
    }).sort_values(('QueueTime', 'mean'), ascending=False)

    # Create formatted version
    formatted_stats = []
    for namespace, row in ns_stats.iterrows():
        mean_time = row[('QueueTime', 'mean')]
        max_time = row[('QueueTime', 'max')]
        count = row[('QueueTime', 'count')]
        
        formatted_stats.append({
            'Namespace': namespace,
            'Mean_Queue_Time': format_time(mean_time),
            'Mean_Seconds': f"{mean_time:.2f}",
            'Max_Queue_Time': format_time(max_time),
            'Max_Seconds': f"{max_time:.2f}",
            'Pod_Count': count
        })

    # Create and display formatted DataFrame
    formatted_df = pd.DataFrame(formatted_stats)
    
    print(f"\nTOP NAMESPACES BY AVERAGE QUEUE TIME:")
    print("-"*70)
    for _, row in formatted_df.head(10).iterrows():
        ns_name = row['Namespace'][:25]
        avg_time = row['Mean_Queue_Time']
        pod_count = row['Pod_Count']
        print(f"{ns_name:<25} {avg_time:<15} ({pod_count} pods)")
    
    print("="*70)

    # Save reports
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save formatted namespace stats
    ns_stats_file = os.path.join(output_dir, f"namespace_stats_{timestamp}.csv")
    formatted_df.to_csv(ns_stats_file, index=False)
    
    # Save deduplicated data
    dedup_file = os.path.join(output_dir, f"deduplicated_data_{timestamp}.csv")
    dedup_data.to_csv(dedup_file, index=False)

    print(f"\nReports saved to: {output_dir}")
    print(f"- Namespace stats: {os.path.basename(ns_stats_file)}")
    print(f"- Processed data: {os.path.basename(dedup_file)}")

if __name__ == "__main__":
    main()
