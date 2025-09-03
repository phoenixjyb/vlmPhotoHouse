#!/usr/bin/env python3
"""
GPU Usage Monitor with Plotting
Monitor GPU usage for 1 minute and create a plot
"""

import subprocess
import time
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import threading

def get_gpu_stats():
    """Get current GPU utilization and memory usage"""
    try:
        result = subprocess.run([
            'nvidia-smi', 
            '--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu', 
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            gpu_data = []
            
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 6:
                    gpu_id, name, util, mem_used, mem_total, temp = parts
                    gpu_data.append({
                        'id': int(gpu_id),
                        'name': name,
                        'utilization': int(util),
                        'memory_used': int(mem_used),
                        'memory_total': int(mem_total),
                        'temperature': int(temp),
                        'memory_percent': (int(mem_used) / int(mem_total)) * 100
                    })
            
            return gpu_data
        else:
            print(f"nvidia-smi error: {result.stderr}")
            return []
            
    except Exception as e:
        print(f"Error getting GPU stats: {e}")
        return []

def monitor_gpu_usage(duration_seconds=60, interval_seconds=2):
    """Monitor GPU usage for specified duration"""
    
    print(f"📊 MONITORING GPU USAGE FOR {duration_seconds} SECONDS")
    print("=" * 60)
    
    # Storage for data
    timestamps = []
    gpu_data = {}
    
    # Initialize data structure
    initial_stats = get_gpu_stats()
    if not initial_stats:
        print("❌ Cannot get GPU stats")
        return
    
    for gpu in initial_stats:
        gpu_id = gpu['id']
        gpu_data[gpu_id] = {
            'name': gpu['name'],
            'utilization': [],
            'memory_percent': [],
            'temperature': []
        }
    
    print(f"Found {len(initial_stats)} GPUs:")
    for gpu in initial_stats:
        print(f"   GPU {gpu['id']}: {gpu['name']}")
    
    print(f"\nStarting monitoring (updating every {interval_seconds}s)...")
    print("Time      | " + " | ".join([f"GPU{gpu['id']} Util%" for gpu in initial_stats]) + " |")
    print("-" * (10 + len(initial_stats) * 15))
    
    start_time = time.time()
    
    while time.time() - start_time < duration_seconds:
        current_time = time.time() - start_time
        timestamps.append(current_time)
        
        # Get current stats
        current_stats = get_gpu_stats()
        
        if current_stats:
            # Display current values
            current_time_str = f"{current_time:6.1f}s"
            util_values = []
            
            for gpu in current_stats:
                gpu_id = gpu['id']
                if gpu_id in gpu_data:
                    gpu_data[gpu_id]['utilization'].append(gpu['utilization'])
                    gpu_data[gpu_id]['memory_percent'].append(gpu['memory_percent'])
                    gpu_data[gpu_id]['temperature'].append(gpu['temperature'])
                    util_values.append(f"GPU{gpu_id}: {gpu['utilization']:3d}%")
            
            print(f"{current_time_str} | " + " | ".join(util_values) + " |")
        
        time.sleep(interval_seconds)
    
    print(f"\n✅ Monitoring complete!")
    return timestamps, gpu_data

def create_gpu_plot(timestamps, gpu_data):
    """Create plots showing GPU utilization over time"""
    
    if not timestamps or not gpu_data:
        print("❌ No data to plot")
        return
    
    # Create subplots
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle('GPU Usage Monitoring (1 Minute)', fontsize=16)
    
    # Colors for different GPUs
    colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown']
    
    # Plot 1: GPU Utilization
    ax1 = axes[0, 0]
    for i, (gpu_id, data) in enumerate(gpu_data.items()):
        if data['utilization']:
            color = colors[i % len(colors)]
            ax1.plot(timestamps, data['utilization'], 
                    label=f"GPU {gpu_id}: {data['name'][:20]}", 
                    color=color, linewidth=2, marker='o', markersize=3)
    
    ax1.set_title('GPU Utilization (%)')
    ax1.set_xlabel('Time (seconds)')
    ax1.set_ylabel('Utilization (%)')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    ax1.set_ylim(0, 100)
    
    # Plot 2: Memory Usage
    ax2 = axes[0, 1]
    for i, (gpu_id, data) in enumerate(gpu_data.items()):
        if data['memory_percent']:
            color = colors[i % len(colors)]
            ax2.plot(timestamps, data['memory_percent'], 
                    label=f"GPU {gpu_id}: {data['name'][:20]}", 
                    color=color, linewidth=2, marker='s', markersize=3)
    
    ax2.set_title('GPU Memory Usage (%)')
    ax2.set_xlabel('Time (seconds)')
    ax2.set_ylabel('Memory Usage (%)')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    ax2.set_ylim(0, 100)
    
    # Plot 3: Temperature
    ax3 = axes[1, 0]
    for i, (gpu_id, data) in enumerate(gpu_data.items()):
        if data['temperature']:
            color = colors[i % len(colors)]
            ax3.plot(timestamps, data['temperature'], 
                    label=f"GPU {gpu_id}: {data['name'][:20]}", 
                    color=color, linewidth=2, marker='^', markersize=3)
    
    ax3.set_title('GPU Temperature (°C)')
    ax3.set_xlabel('Time (seconds)')
    ax3.set_ylabel('Temperature (°C)')
    ax3.grid(True, alpha=0.3)
    ax3.legend()
    
    # Plot 4: Summary Stats
    ax4 = axes[1, 1]
    ax4.axis('off')
    
    # Calculate summary statistics
    summary_text = "📊 SUMMARY STATISTICS\n\n"
    
    for gpu_id, data in gpu_data.items():
        if data['utilization']:
            avg_util = np.mean(data['utilization'])
            max_util = np.max(data['utilization'])
            avg_mem = np.mean(data['memory_percent'])
            max_temp = np.max(data['temperature'])
            
            summary_text += f"GPU {gpu_id}: {data['name'][:25]}\n"
            summary_text += f"  Avg Utilization: {avg_util:.1f}%\n"
            summary_text += f"  Max Utilization: {max_util:.1f}%\n"
            summary_text += f"  Avg Memory: {avg_mem:.1f}%\n"
            summary_text += f"  Max Temperature: {max_temp}°C\n\n"
            
            # Determine if this GPU was actively used
            if avg_util > 10:
                summary_text += f"  🔥 HIGH USAGE - Face detection likely using this GPU!\n\n"
            elif avg_util > 1:
                summary_text += f"  ⚡ Some usage detected\n\n"
            else:
                summary_text += f"  💤 Idle during monitoring\n\n"
    
    ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes, 
             fontsize=10, verticalalignment='top', fontfamily='monospace')
    
    plt.tight_layout()
    
    # Save plot
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gpu_monitoring_{timestamp}.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    
    print(f"📈 Plot saved as: {filename}")
    
    # Show plot
    plt.show()

def main():
    """Main monitoring function"""
    
    print("🎮 GPU USAGE MONITOR")
    print("=" * 40)
    print("This will monitor GPU usage for 1 minute and create a plot.")
    print("Start face detection processing in another terminal to see usage!")
    print()
    
    # Start monitoring
    timestamps, gpu_data = monitor_gpu_usage(duration_seconds=60, interval_seconds=2)
    
    if timestamps and gpu_data:
        print(f"\n📈 Creating plots...")
        create_gpu_plot(timestamps, gpu_data)
        
        # Analysis
        print(f"\n🔍 ANALYSIS:")
        for gpu_id, data in gpu_data.items():
            if data['utilization']:
                avg_util = np.mean(data['utilization'])
                if avg_util > 10:
                    print(f"✅ GPU {gpu_id} ({data['name']}) shows high usage - likely processing faces!")
                elif avg_util > 1:
                    print(f"⚠️ GPU {gpu_id} ({data['name']}) shows some usage")
                else:
                    print(f"💤 GPU {gpu_id} ({data['name']}) was idle")
    else:
        print("❌ No data collected")

if __name__ == "__main__":
    main()
