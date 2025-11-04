#!/bin/bash

# System Information Script
# Displays main system information

echo "========================================"
echo "           SYSTEM INFORMATION           "
echo "========================================"
echo

# Operating System Information
echo "🖥️  OPERATING SYSTEM:"
if [ -f /etc/os-release ]; then
    source /etc/os-release
    echo "   Distribution: $PRETTY_NAME"
    echo "   Version: $VERSION"
elif [ -f /etc/redhat-release ]; then
    echo "   Distribution: $(cat /etc/redhat-release)"
else
    echo "   Distribution: $(uname -s)"
fi
echo

# Kernel Information
echo "🔧 KERNEL:"
echo "   Version: $(uname -r)"
echo "   Architecture: $(uname -m)"
echo

# System Uptime
echo "⏰ UPTIME:"
uptime -p 2>/dev/null || uptime
echo

# Memory Information
echo "💾 MEMORY:"
if command -v free >/dev/null 2>&1; then
    free -h | head -2 | awk 'NR==1{print "   Total: " $2} NR==2{print "   Used:  " $3 " / Available: " $7}'
else
    echo "   Memory info not available"
fi
echo

# Disk Usage
echo "💽 DISK USAGE:"
df -h / | tail -1 | awk '{print "   Root: " $3 " / " $2 " (" $5 " used)"}'
if [ -d /home ]; then
    df -h /home 2>/dev/null | tail -1 | awk '{print "   Home: " $3 " / " $2 " (" $5 " used)"}' || true
fi
echo

# CPU Information
echo "🖥️  CPU:"
if [ -f /proc/cpuinfo ]; then
    cpu_model=$(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
    cpu_cores=$(nproc)
    if [ -n "$cpu_model" ]; then
        echo "   Model: $cpu_model"
        echo "   Cores: $cpu_cores"
    else
        echo "   Processor: $(grep -m1 "vendor_id\|model\|cpu " /proc/cpuinfo | cut -d: -f2 | xargs)"
    fi
else
    echo "   CPU info not available"
fi
echo

# Network Information
echo "🌐 NETWORK:"
hostname -I 2>/dev/null | awk '{print "   IP Address: " $1}' || echo "   IP Address: Not available"
echo "   Hostname: $(hostname)"
echo

# Load Average
echo "📊 LOAD AVERAGE:"
echo "   $(uptime | awk -F'load average:' '{print $2}')"

echo
echo "========================================"