# Complete Shell Toolset for Rootfs

## All Commands Included (Categorized)

### Text Processing & Search (14 commands)
```bash
grep, egrep, fgrep    # Search patterns in files
sed                   # Stream editor (find/replace)
awk                   # Pattern scanning and processing
cut                   # Extract columns/fields
paste                 # Merge lines from files
join                  # Join lines on common field
tr                    # Translate/delete characters
sort                  # Sort lines
uniq                  # Remove duplicate lines
head, tail            # First/last N lines
wc                    # Count lines/words/chars
diff, comm            # Compare files
column                # Format output in columns
```

### File Operations (15 commands)
```bash
cp, mv, rm            # Copy, move, delete
mkdir, rmdir          # Create/remove directories
touch                 # Create empty files, update timestamps
cat, tac              # Concatenate, reverse concatenate
less, more            # Page through files
find                  # Search for files
xargs                 # Build command lines from input
ln                    # Create symlinks
ls                    # List directory contents
chmod, chown          # Change permissions/ownership
```

### Data Processing Tools (8 commands)
```bash
jq                    # JSON processor - parse, filter, transform JSON
csvcut                # Extract columns from CSV
csvgrep               # Filter CSV rows
csvjoin               # Join CSV files
csvstat               # Statistics on CSV columns
csvlook               # Pretty-print CSV
sqlite3               # SQL database queries
bc                    # Arbitrary precision calculator
date                  # Display/format dates
seq                   # Generate number sequences
```

### Compression & Archives (12 commands)
```bash
gzip, gunzip, zcat    # gzip compression
bzip2, bunzip2, bzcat # bzip2 compression
xz, unxz, xzcat       # xz compression
zip, unzip            # zip archives
tar                   # Tape archiver
```

### Network Tools (3 commands, optional)
```bash
curl                  # HTTP client, download files
wget                  # Download files from web
nc                    # Netcat - network Swiss Army knife
```

### Text Editors (3 editors)
```bash
vim                   # Full-featured text editor
nano                  # Simple text editor
ed                    # Line-oriented editor
```

### Development Tools (3 commands)
```bash
git                   # Version control
make                  # Build automation
env                   # Display/set environment variables
```

### Utilities (10 commands)
```bash
echo                  # Print text
printf                # Formatted output
test, [               # Condition testing
expr                  # Evaluate expressions
basename, dirname     # Path manipulation
which, whereis        # Locate commands
file                  # Determine file type
stat                  # File statistics
```

---

## Enhanced Manifest Structure

### /etc/sandbox_manifest.json (Full)

```json
{
  "manifest_version": "1.0",
  "image": {
    "name": "py-data-3.11",
    "version": "1.0.0",
    "build_date": "2024-11-05",
    "sha256": "abc123..."
  },
  "os": {
    "distribution": "debian",
    "release": "bookworm",
    "snapshot_date": "2024-10-01"
  },
  "python": {
    "version": "3.11.9",
    "path": "/opt/venv/bin/python3",
    "pip_version": "24.0"
  },
  "python_packages": {
    "numpy": "1.26.4",
    "pandas": "2.2.2",
    "scipy": "1.13.0",
    "scikit-learn": "1.4.2",
    "pyarrow": "16.0.0",
    "matplotlib": "3.8.4",
    "polars": "0.20.0",
    "requests": "2.31.0",
    "openpyxl": "3.1.2"
  },
  "shell_commands": {
    "text_processing": [
      "grep", "egrep", "fgrep", "sed", "awk", 
      "cut", "paste", "join", "tr", "sort", 
      "uniq", "head", "tail", "wc", "diff", 
      "comm", "column"
    ],
    "file_operations": [
      "cp", "mv", "rm", "mkdir", "rmdir", 
      "touch", "cat", "tac", "less", "more", 
      "find", "xargs", "ln", "ls", "chmod"
    ],
    "data_tools": [
      "jq", "csvcut", "csvgrep", "csvjoin", 
      "csvstat", "csvlook", "sqlite3", "bc", 
      "date", "seq"
    ],
    "compression": [
      "gzip", "gunzip", "zcat", "bzip2", 
      "bunzip2", "bzcat", "xz", "unxz", 
      "xzcat", "zip", "unzip", "tar"
    ],
    "network": ["curl", "wget", "nc"],
    "editors": ["vim", "nano", "ed"],
    "development": ["git", "make", "env"],
    "utilities": [
      "echo", "printf", "test", "expr", 
      "basename", "dirname", "which", 
      "whereis", "file", "stat"
    ]
  },
  "command_examples": {
    "jq": {
      "description": "Parse and transform JSON",
      "examples": [
        "jq '.' file.json                    # Pretty-print JSON",
        "jq '.field' file.json               # Extract field",
        "jq -r '.[] | .name' file.json       # Array iteration"
      ]
    },
    "csvcut": {
      "description": "Extract columns from CSV",
      "examples": [
        "csvcut -c 1,3 file.csv              # Columns 1 and 3",
        "csvcut -c name,age file.csv         # Named columns"
      ]
    },
    "csvgrep": {
      "description": "Filter CSV rows",
      "examples": [
        "csvgrep -c age -r '^[3-9]' data.csv # Regex match",
        "csvgrep -c city -m 'Boston' data.csv # Exact match"
      ]
    },
    "csvjoin": {
      "description": "Join CSV files",
      "examples": [
        "csvjoin -c id file1.csv file2.csv   # Join on 'id' column"
      ]
    },
    "awk": {
      "description": "Pattern scanning and text processing",
      "examples": [
        "awk '{print $1}' file.txt           # First column",
        "awk -F, '{print $2}' file.csv       # CSV second column",
        "awk '$3 > 100' data.txt             # Filter rows"
      ]
    },
    "sed": {
      "description": "Stream editor for text transformation",
      "examples": [
        "sed 's/old/new/' file.txt           # Replace first occurrence",
        "sed 's/old/new/g' file.txt          # Replace all",
        "sed -n '5,10p' file.txt             # Lines 5-10"
      ]
    },
    "bc": {
      "description": "Arbitrary precision calculator",
      "examples": [
        "echo '2+2' | bc                     # Simple math",
        "echo 'scale=2; 10/3' | bc           # Decimals",
        "echo 'sqrt(16)' | bc -l             # Math library"
      ]
    },
    "sqlite3": {
      "description": "SQL database queries",
      "examples": [
        "sqlite3 db.sqlite 'SELECT * FROM users;'",
        "sqlite3 :memory: '.read schema.sql' '.dump'"
      ]
    }
  },
  "environment": {
    "PATH": "/opt/venv/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1"
  },
  "capabilities": {
    "networking": false,
    "gpu": false,
    "max_processes": 64,
    "max_memory_mb": 1024,
    "writable_paths": ["/workspace", "/tmp"]
  }
}
```

---

## Agent Integration - System Prompt Enhancement

```python
# In agent.py _build_system_prompt()

def _load_sandbox_manifest():
    """Load manifest from rootfs or default"""
    manifest_path = "/etc/sandbox_manifest.json"
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            return json.load(f)
    return None

def _build_system_prompt(self, system_context: str) -> str:
    tools_block = self._format_tools_for_prompt()
    
    # Load sandbox capabilities
    manifest = _load_sandbox_manifest()
    sandbox_info = ""
    
    if manifest:
        # Python info
        py_ver = manifest['python']['version']
        packages = manifest['python_packages']
        pkg_list = ', '.join(f"{k} {v}" for k, v in list(packages.items())[:6])
        
        # Shell commands by category
        data_tools = ', '.join(manifest['shell_commands']['data_tools'])
        text_tools = ', '.join(manifest['shell_commands']['text_processing'][:10])
        
        sandbox_info = f"""
Sandbox Environment (Isolated):
- Python {py_ver} with packages: {pkg_list}
- Data tools: {data_tools}
- Text processing: {text_tools}, ...
- See /etc/sandbox_manifest.json for complete tool list and examples

Command examples:
- JSON: echo '{{"a":1}}' | jq .a
- CSV columns: csvcut -c 1,3 data.csv
- CSV filter: csvgrep -c age -r '^[3-9]' data.csv
- Math: echo 'scale=2; 10/3' | bc
- SQL: sqlite3 data.db 'SELECT * FROM users WHERE age > 30;'
"""
    
    return f"""Shell automation expert and conversational assistant.

{tools_block}

{system_context}

{sandbox_info}

File access model:
[... rest of prompt ...]
"""
```

---

## Total Tool Count Summary

- **Text Processing:** 17 commands
- **File Operations:** 15 commands
- **Data Processing:** 10 commands (including csvkit suite)
- **Compression:** 12 commands
- **Network:** 3 commands
- **Editors:** 3 commands
- **Development:** 3 commands
- **Utilities:** 10 commands
- **Python packages:** 9 major libraries

**Total: ~70+ shell commands + Python data stack**

All available, all known to agent via manifest.

---

## Build Script Addition

```bash
# In rootfs build script

# Install all data manipulation tools
apt-get install -y --no-install-recommends \
  coreutils \
  grep sed gawk \
  findutils \
  diffutils \
  tar gzip bzip2 xz-utils zip unzip \
  jq \
  csvkit \
  sqlite3 \
  bc \
  curl wget netcat-openbsd \
  vim nano ed \
  git make \
  python3.11 python3-pip

# Verify all tools present
for cmd in grep sed awk jq csvcut csvgrep csvjoin bc sqlite3 curl; do
  which $cmd || { echo "Missing: $cmd"; exit 1; }
done

echo "✓ All shell tools installed"
```

---

## Agent Can Now:

1. **Query manifest** to know exact capabilities
2. **Use csvkit** for complex CSV operations (join, filter, stats)
3. **Use jq** for JSON parsing/transformation
4. **Use sqlite3** for SQL queries on data
5. **Use bc** for calculations
6. **Use awk/sed** for text processing
7. **Combine tools** in pipelines: `csvcut -c 1,3 data.csv | csvgrep -c age -r '^[3-9]' | csvstat`

The agent will have a complete data manipulation toolkit at its disposal.
