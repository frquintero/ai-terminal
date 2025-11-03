"""
System Information Utility

Gathers system context (OS, hardware, memory, filesystem) for the AI agent.
"""

import os
import platform
import subprocess
import shutil
from typing import Dict, Optional

def get_command_output(cmd: str) -> Optional[str]:
    """Execute a command and return its output, or None if it fails"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=2
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None

def get_distro_info() -> Optional[str]:
    """Parse distribution info from /etc/os-release with Python fallback"""
    try:
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if line.startswith('PRETTY_NAME='):
                    return line.split('=', 1)[1].strip().strip('"')
    except Exception:
        pass
    return None

def get_memory_info() -> tuple:
    """Get memory info with fallback to /proc/meminfo"""
    # Try free command first
    mem_total = get_command_output('LC_ALL=C free -h | grep Mem | awk \'{print $2}\'')
    mem_available = get_command_output('LC_ALL=C free -h | grep Mem | awk \'{print $7}\'')
    
    if mem_total and mem_available:
        return (mem_total, mem_available)
    
    # Fallback to /proc/meminfo
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.read()
            total_kb = None
            avail_kb = None
            for line in meminfo.split('\n'):
                if line.startswith('MemTotal:'):
                    total_kb = int(line.split()[1])
                elif line.startswith('MemAvailable:'):
                    avail_kb = int(line.split()[1])
            
            if total_kb and avail_kb:
                # Convert to human-readable format
                return (f"{total_kb // 1024}M", f"{avail_kb // 1024}M")
    except Exception:
        pass
    
    return (None, None)

def get_cpu_info() -> tuple:
    """Get CPU info with fallback to /proc/cpuinfo"""
    # Try lscpu first
    cpu_model = get_command_output('LC_ALL=C lscpu | grep "Model name" | cut -d":" -f2 | xargs')
    cpu_cores = get_command_output('nproc')
    
    if cpu_model and cpu_cores:
        return (cpu_model, cpu_cores)
    
    # Fallback to /proc/cpuinfo
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            model = None
            cores = 0
            for line in cpuinfo.split('\n'):
                if not model and line.startswith('model name'):
                    model = line.split(':', 1)[1].strip()
                if line.startswith('processor'):
                    cores += 1
            
            if model and cores > 0:
                return (model, str(cores))
    except Exception:
        pass
    
    return (cpu_model, cpu_cores)

def get_git_info() -> Dict[str, str]:
    """Gather git repository information for the current working directory"""
    git_info = {}
    
    # Check if git is available
    if not shutil.which('git'):
        return git_info
    
    # Check if we're in a git repository
    in_repo = get_command_output('git rev-parse --is-inside-work-tree')
    if in_repo != 'true':
        return git_info
    
    # Get repository root
    repo_root = get_command_output('git rev-parse --show-toplevel')
    if repo_root:
        git_info['repo_root'] = repo_root
    
    # Get current branch
    branch = get_command_output('git rev-parse --abbrev-ref HEAD')
    if branch:
        git_info['branch'] = branch
    
    # Get current commit hash (short)
    commit_hash = get_command_output('git rev-parse --short HEAD')
    if commit_hash:
        git_info['commit'] = commit_hash
    
    # Get repository name (from remote origin)
    repo_name = get_command_output('git rev-parse --abbrev-ref --symbolic-full-name @{u} | cut -d"/" -f1')
    if not repo_name:
        # Fallback: get from remote origin URL
        origin_url = get_command_output('git config --get remote.origin.url')
        if origin_url:
            # Extract repo name from URL (e.g., git@github.com:user/repo.git -> repo)
            repo_name = origin_url.rstrip('/').split('/')[-1].replace('.git', '')
    if repo_name:
        git_info['repo_name'] = repo_name
    
    # Get remote origin URL
    origin_url = get_command_output('git config --get remote.origin.url')
    if origin_url:
        git_info['origin'] = origin_url
    
    # Check if there are uncommitted changes
    uncommitted = get_command_output('git status --porcelain')
    if uncommitted:
        # Count the number of changes
        change_count = len(uncommitted.strip().split('\n'))
        git_info['uncommitted_changes'] = str(change_count)
    
    return git_info

def get_system_info() -> Dict[str, str]:
    """Gather comprehensive system information"""
    info = {}
    
    # Basic OS info
    info['os'] = platform.system()
    info['os_version'] = platform.version()
    info['architecture'] = platform.machine()
    info['hostname'] = platform.node()
    info['python_version'] = platform.python_version()
    
    # Linux-specific details
    if info['os'] == 'Linux':
        # Distribution info with Python fallback
        distro_info = get_distro_info()
        if distro_info:
            info['distribution'] = distro_info
        
        # Kernel version
        kernel = get_command_output('uname -r')
        if kernel:
            info['kernel'] = kernel
        
        # Shell
        shell = os.environ.get('SHELL', 'unknown')
        info['shell'] = shell
        
        # CPU info with fallback
        cpu_model, cpu_cores = get_cpu_info()
        if cpu_model:
            info['cpu'] = cpu_model
        if cpu_cores:
            info['cpu_cores'] = cpu_cores
        
        # Memory with fallback
        mem_total, mem_available = get_memory_info()
        if mem_total:
            info['memory_total'] = mem_total
        if mem_available:
            info['memory_available'] = mem_available
        
        # Disk space
        disk_info = get_command_output('LC_ALL=C df -h / | tail -1 | awk \'{print $2" total, "$4" available"}\'')
        if disk_info:
            info['disk_root'] = disk_info
    
    # User info
    info['user'] = os.environ.get('USER', 'unknown')
    info['home'] = os.path.expanduser('~')
    
    # PATH environment variable
    path = os.environ.get('PATH', '')
    if path:
        info['path'] = path
    
    # Check for common tools
    common_tools = ['git', 'docker', 'curl', 'wget', 'vim', 'nano', 'systemctl', 'apt', 'yum', 'dnf']
    available_tools = [tool for tool in common_tools if shutil.which(tool)]
    if available_tools:
        info['available_tools'] = ', '.join(available_tools)
    
    # Git information (if in a git repository)
    git_info = get_git_info()
    info.update(git_info)
    
    return info

def format_system_info(info: Dict[str, str]) -> str:
    """Format system info as a compact string for the AI agent"""
    lines = []
    
    # System: OS, shell, hardware resources
    os_name = info.get('distribution', info['os']).split('(')[0].strip()  # Remove redundant arch
    shell = info.get('shell', '').split('/')[-1] if 'shell' in info else 'unknown'
    cores = info.get('cpu_cores', '?')
    mem_total = info.get('memory_total', '?')
    mem_avail = info.get('memory_available', '?')
    disk = info.get('disk_root', '?')
    
    lines.append(f"System: {os_name}, {shell} shell, {cores} cores, {mem_total} RAM ({mem_avail} free), {disk} disk")
    
    # User context
    lines.append(f"User: {info['user']} (home: {info['home']})")
    
    # PATH environment variable
    if 'path' in info:
        path_dirs = info['path'].split(':')
        path_summary = ':'.join(path_dirs[:5])  # Show first 5 directories
        if len(path_dirs) > 5:
            path_summary += f":... ({len(path_dirs)} total)"
        lines.append(f"PATH: {path_summary}")
    
    # Available tools (if any)
    if 'available_tools' in info:
        lines.append(f"Tools: {info['available_tools']}")
    
    # Git information (if available)
    if 'repo_name' in info:
        git_line = f"Git: {info['repo_name']}"
        if 'branch' in info:
            git_line += f" @ {info['branch']}"
        if 'commit' in info:
            git_line += f" ({info['commit'][:7]})"
        if 'uncommitted_changes' in info:
            git_line += f" [{info['uncommitted_changes']} changes]"
        lines.append(git_line)
    
    return '\n'.join(lines)
