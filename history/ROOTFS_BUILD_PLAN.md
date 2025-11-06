# Rootfs Build Plan - Simple Explanation

## What We're Building
A folder that looks like a complete Linux system, but only contains what we need.

## Directory Structure
```
rootfs/
├── bin/          # Basic commands (bash, ls, cat, grep, etc.)
├── usr/
│   ├── bin/      # More commands (python3, jq, curl)
│   └── lib/      # Shared libraries
├── lib/          # System libraries
├── lib64/        # 64-bit libraries
├── etc/
│   └── sandbox_manifest.json  # What the agent reads to know what's available
├── opt/
│   └── venv/     # Python packages (pandas, numpy, etc.)
│       ├── bin/
│       │   └── python -> /usr/bin/python3.11
│       └── lib/python3.11/site-packages/
│           ├── pandas/
│           ├── numpy/
│           ├── scipy/
│           └── ...
├── tmp/          # Temporary files (will be tmpfs at runtime)
├── proc/         # Process info (will be mounted at runtime)
└── dev/          # Devices (will be mounted at runtime)
```

## How We Populate It (Step by Step)

### Step 1: Get Base System Files
Use `debootstrap` or download minimal Debian/Ubuntu:
```bash
# Create minimal Debian base
debootstrap --variant=minbase stable rootfs/ http://snapshot.debian.org/archive/debian/20241001T000000Z/
```

**This gives us:** bash, coreutils (ls, cat, grep, etc.), basic libraries

### Step 2: Install System Tools
```bash
# Enter the rootfs and install tools
chroot rootfs/ apt-get install -y \
  python3.11 \
  curl \
  jq \
  git \
  vim \
  gzip \
  tar
```

**This adds:** Python binary, JSON processor, compression tools

### Step 3: Create Python Environment
```bash
# Inside rootfs, create venv
chroot rootfs/ python3.11 -m venv /opt/venv

# Install data packages with LOCKED versions
chroot rootfs/ /opt/venv/bin/pip install \
  numpy==1.26.4 \
  pandas==2.2.2 \
  scipy==1.13.0 \
  scikit-learn==1.4.2 \
  pyarrow==16.0.0 \
  matplotlib==3.8.4
```

**This creates:** /opt/venv with exactly these package versions

### Step 4: Generate Manifest
```bash
# Create manifest.json that agent will read
cat > rootfs/etc/sandbox_manifest.json <<EOF
{
  "os": "debian-stable-20241001",
  "python": "3.11.9",
  "packages": {
    "numpy": "1.26.4",
    "pandas": "2.2.2",
    "scipy": "1.13.0",
    "scikit-learn": "1.4.2",
    "pyarrow": "16.0.0",
    "matplotlib": "3.8.4"
  },
  "shell": {
    "bash": "5.2",
    "grep": "3.11",
    "jq": "1.7",
    "curl": "8.5"
  }
}
EOF
```

**This tells agent:** "You have pandas 2.2.2, numpy 1.26.4, etc."

### Step 5: Make It Immutable
```bash
# Make everything read-only (can't be modified)
chmod -R a-w rootfs/

# Create tarball or squashfs
tar czf py-data-3.11-rootfs.tar.gz -C rootfs/ .
# OR
mksquashfs rootfs/ py-data-3.11.squashfs -comp zstd
```

**This creates:** Single file containing entire environment

### Step 6: Cache Locally
```bash
# Store by content hash
SHA256=$(sha256sum py-data-3.11-rootfs.tar.gz | cut -d' ' -f1)
mkdir -p ~/.cache/agent_sandbox/images/
mv py-data-3.11-rootfs.tar.gz ~/.cache/agent_sandbox/images/$SHA256.tar.gz
```

**This stores:** Reusable rootfs in cache directory

## How Agent Uses It (Runtime)

### Step 7: Extract and Enter
```python
# In ShellIntegration.__init__()
rootfs_path = extract_rootfs(sha256='abc123...')
# Extracts to: /tmp/rootfs-abc123/

# Launch shell INSIDE the rootfs
self.shell = pexpect.spawn(
    'bwrap',
    [
        '--unshare-all',              # Isolate everything
        '--ro-bind', rootfs_path, '/',  # Mount rootfs as /
        '--tmpfs', '/tmp',            # Fresh /tmp
        '--proc', '/proc',            # Process info
        '--dev', '/dev',              # Devices
        '--bind', working_dir, '/workspace',  # Our files (RW)
        '--setenv', 'PATH', '/opt/venv/bin:/usr/bin:/bin',
        '--setenv', 'HOME', '/workspace',
        '--chdir', '/workspace',
        '/bin/bash', '-i'
    ]
)
```

**Result:** Shell runs inside rootfs, sees ONLY what we put there

### Step 8: Agent Knows What's Available
```python
# In agent.py startup
manifest = read_rootfs_manifest()
# Returns: {"python": "3.11.9", "packages": {"pandas": "2.2.2", ...}}

# Update system prompt
system_prompt += f"""
Available tools in sandbox:
- Python {manifest['python']}
- pandas {manifest['packages']['pandas']}
- numpy {manifest['packages']['numpy']}
- jq {manifest['shell']['jq']}
"""
```

**Agent now knows:** Exact versions, can plan accordingly

## What User Sees

### Before (Current)
- Agent runs commands on YOUR system
- Uses YOUR Python, YOUR packages
- Versions unpredictable
- Could break YOUR system

### After (With Rootfs)
- Agent runs commands in ISOLATED rootfs
- Uses CONTROLLED Python 3.11.9, pandas 2.2.2
- Versions always the same
- CANNOT break your system (read-only)
- Can only write to /workspace (working directory)

## Example Command Execution

User asks: "Show me pandas version"

### Current Behavior
```bash
$ python3 -c "import pandas; print(pandas.__version__)"
# Uses YOUR python, YOUR pandas (maybe 1.5.3, maybe 2.1.0, who knows?)
```

### New Behavior
```bash
# Agent spawns in rootfs
$ python3 -c "import pandas; print(pandas.__version__)"
2.2.2
# ALWAYS 2.2.2, because that's what's in the rootfs
```

## Two Images We'll Build

### 1. py-vanilla-3.11 (~200MB)
- Python 3.11.9
- bash, grep, sed, awk, jq, curl
- NO data packages
- For general scripting

### 2. py-data-3.11 (~500MB)
- Everything from py-vanilla
- PLUS: numpy, pandas, scipy, sklearn, pyarrow, matplotlib
- For data analysis

## Key Benefits

1. **Deterministic:** Same tools every time
2. **Isolated:** Can't touch your system
3. **Known:** Agent reads manifest, knows exactly what's available
4. **Reproducible:** Same results on any Linux machine
5. **Safe:** Read-only, can only write to working directory

## Implementation Complexity

- Build script: 1 day
- Integration with ShellIntegration: 1 day
- Testing: 1 day
- CI/publishing: 1 day

**Total: 3-4 days**
