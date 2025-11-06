# Namespace Isolation

Optional Linux namespace isolation for AI Terminal using deterministic rootfs and bubblewrap.

## Overview

The agent can run commands in two modes:

### Direct Mode (Default)
- Commands execute on your host system
- Uses your Python, packages, and tools
- Full system access
- No overhead

### Isolated Mode (Opt-in)
- Commands execute inside isolated Linux namespace
- Deterministic Python 3.11.9 + data science stack
- Controlled toolset (70+ shell commands)
- Read-only rootfs, writable workspace only
- Prevents accidental system damage

## Benefits of Isolation

**Security:**
- Cannot `rm -rf /` your host
- Cannot read `~/.ssh` or other secrets
- Cannot kill host processes
- Network disabled by default

**Determinism:**
- Same Python version (3.11.9) everywhere
- Locked package versions (pandas 2.2.2, numpy 1.26.4, etc.)
- Same shell tools regardless of host
- Agent knows exact capabilities via manifest

**Reproducibility:**
- Same results across different machines
- No "works on my machine" issues
- Consistent for data analysis workflows

## Quick Start

### 1. Build Rootfs (One-time)

The script will **auto-install debootstrap** if missing (detects your package manager):

```bash
# Requires: root privileges, ~500MB disk space
sudo ./build_rootfs.sh

# If debootstrap is missing, the script will:
# [INFO] debootstrap not found, attempting auto-install...
# [INFO] Detected Manjaro Linux
# [INFO] Installing debootstrap with pacman...
# [INFO] ✓ debootstrap installed successfully

# Then builds the rootfs:
# ========================================
# Image: py-data-3.11
# SHA256: abc123...
# Path: ~/.cache/agent_sandbox/images/abc123....tar.gz
# Size: 487M
# ========================================
```

**Supported distros for auto-install:** Arch, Manjaro, Debian, Ubuntu, Fedora, RHEL, openSUSE

**Manual install (if needed):**
```bash
# Arch/Manjaro
sudo pacman -S debootstrap

# Debian/Ubuntu
sudo apt-get install debootstrap

# Fedora/RHEL
sudo dnf install debootstrap
```

This creates a minimal Debian rootfs with:
- Python 3.11.9 + venv at /opt/venv
- Data packages: numpy, pandas, scipy, scikit-learn, pyarrow, matplotlib, polars
- Shell tools: grep, sed, awk, jq, csvkit, sqlite3, bc, curl, wget, git
- Manifest: /etc/sandbox_manifest.json

### 2. Enable Isolation

```bash
# Use isolated mode
export SANDBOX_ENABLE_ISOLATION=1

# Run agent (will auto-extract and enter rootfs)
python main.py
```

### 3. Verify Isolation

Inside the agent, run:
```
show me the python version and where pandas is installed
```

**Isolated mode output:**
```
Python 3.11.9
pandas location: /opt/venv/lib/python3.11/site-packages/pandas
```

**Direct mode output:**
```
Python 3.13.7
pandas location: /usr/lib/python3.13/site-packages/pandas
```

## Architecture

### Rootfs Structure

```
rootfs/
├── bin/, usr/, lib/, etc/       # Debian base system
├── opt/venv/                    # Python virtual environment
│   ├── bin/python3              # Python 3.11.9
│   └── lib/python3.11/site-packages/
│       ├── numpy/               # 1.26.4
│       ├── pandas/              # 2.2.2
│       └── ...
└── etc/sandbox_manifest.json    # Agent reads this
```

### Runtime Isolation (bubblewrap)

```bash
bwrap \
  --unshare-all \              # Isolate user/mount/PID/net/IPC/UTS namespaces
  --ro-bind /path/to/rootfs / \  # Mount rootfs as / (read-only)
  --tmpfs /tmp \               # Fresh /tmp
  --bind $WORKING_DIR /workspace \  # Your files (read-write)
  --setenv PATH /opt/venv/bin:/usr/bin \
  -- /bin/bash -i
```

**Result:**
- Agent sees only rootfs contents at /
- Can read/write only /workspace (maps to ai-terminal-wd/)
- Cannot see your /home, /root, or other host paths
- No network access (can be enabled if needed)

### Agent Integration

1. **ShellIntegration** detects `SANDBOX_ENABLE_ISOLATION=1`
2. Calls `sandbox_rootfs.extract_rootfs()` to get rootfs path
3. Spawns `bwrap` instead of direct `bash`
4. All commands execute inside isolated environment
5. **Stateless behavior preserved:** Each `run_command` resets to `/workspace`

6. **Agent** loads `/etc/sandbox_manifest.json` on startup
7. Enhances system prompt with available tools
8. Agent knows exactly what's available (Python 3.11.9, pandas 2.2.2, jq 1.7, etc.)

## Available Tools in Rootfs

### Python Stack
- **Python:** 3.11.9 at /opt/venv/bin/python3
- **Packages:** numpy 1.26.4, pandas 2.2.2, scipy 1.13.0, scikit-learn 1.4.2, pyarrow 16.0.0, matplotlib 3.8.4, polars 0.20.31, requests 2.32.0, openpyxl 3.1.2

### Shell Commands (70+)

**Data Processing:**
- jq (JSON processor)
- csvcut, csvgrep, csvjoin, csvstat, csvlook (CSV operations)
- sqlite3 (SQL queries)
- bc (calculator)

**Text Processing:**
- grep, sed, awk, cut, paste, join, sort, uniq, head, tail, wc, diff, comm, column

**File Operations:**
- cp, mv, rm, mkdir, touch, cat, less, more, find, xargs, ln, ls

**Compression:**
- gzip, bzip2, xz, zip, tar (all variants)

**Network:**
- curl, wget (network disabled by default)

**Editors:**
- vim, nano

**Development:**
- git, make

See full list in `/etc/sandbox_manifest.json` inside rootfs.

## Configuration

### Environment Variables

```bash
# Enable/disable isolation
SANDBOX_ENABLE_ISOLATION=1|0         # Default: 0 (disabled)

# Specify rootfs by SHA256
SANDBOX_ROOTFS_SHA256=abc123...      # Default: use latest symlink

# Network access (advanced)
SANDBOX_ENABLE_NETWORK=1|0           # Default: 0 (no network)
```

### Rootfs Management

```bash
# List cached images
python sandbox_rootfs.py list

# Show current image info
python sandbox_rootfs.py info

# Cleanup old extractions (keep latest 2)
python -c "from sandbox_rootfs import cleanup_old_extractions; cleanup_old_extractions()"
```

## Building Custom Rootfs

To customize the rootfs (add packages, change versions):

1. Edit `build_rootfs.sh`:
   ```bash
   # In setup_python_env(), add packages:
   /opt/venv/bin/pip install --no-cache-dir \
       your-package==1.0.0
   ```

2. Rebuild:
   ```bash
   sudo ./build_rootfs.sh
   ```

3. New SHA256 will be generated and cached

## Compatibility

### Supported Platforms
- ✅ Linux (tested on Manjaro, Ubuntu, Debian)
- ❌ macOS (no Linux namespaces)
- ❌ Windows (no Linux namespaces)

### Requirements
- **Build:** debootstrap, root access, ~500MB disk
- **Runtime:** bubblewrap (bwrap), Linux kernel ≥3.8
- **Fallback:** If bwrap unavailable, falls back to direct mode with warning

Install bwrap:
```bash
# Debian/Ubuntu
sudo apt-get install bubblewrap

# Arch/Manjaro
sudo pacman -S bubblewrap

# Fedora
sudo dnf install bubblewrap
```

## Comparison with run_python_sandbox

| Feature | run_python_sandbox | Isolated Shell |
|---------|-------------------|----------------|
| Scope | Python scripts only | All commands |
| Isolation | Resource limits (RLIMIT) | Linux namespaces |
| Root access | No | No (user namespace) |
| Network | Optional | Disabled by default |
| Determinism | Same Python, varies by host | Fully deterministic |
| Overhead | Low | Medium (extraction once) |

**Recommendation:** Use both!
- `run_python_sandbox`: For safe Python execution (unchanged)
- Isolated shell: For deterministic data workflows with guaranteed toolset

## Troubleshooting

### "Warning: bwrap not found"
Install bubblewrap package (see Requirements above)

### "Rootfs not found in cache"
Run `sudo ./build_rootfs.sh` to build rootfs

### "Failed to setup isolation"
Check logs, ensure:
- Linux kernel ≥3.8
- User namespaces enabled: `cat /proc/sys/kernel/unprivileged_userns_clone` should be 1
- bwrap installed and in PATH

### Commands fail inside isolated mode
Check if you're trying to access host paths. Remember:
- Host files: Not visible (except /workspace)
- Use `/workspace` for all file I/O
- Project files: Not accessible in isolated mode (by design)

## Regression Tests

Namespace confusion fix tests still pass:
```bash
python test_namespace_fix.py
# All 5 tests pass ✅
```

## Future Enhancements

- [ ] Multiple rootfs images (py-vanilla, py-ml, py-data)
- [ ] GPU support (passthrough CUDA devices)
- [ ] Optional project directory RO bind
- [ ] Networking toggle via runtime flag
- [ ] OCI image format for broader compatibility

## References

- Epic: ai-terminal-k5j
- Planning: history/ROOTFS_BUILD_PLAN.md
- Toolset: history/SHELL_TOOLSET.md
- Thread: T-cb7cf7bc-2f2b-41d0-85c5-5c5ef3256a2d
