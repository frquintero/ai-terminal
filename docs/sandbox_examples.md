# Python Sandbox Examples

The Python sandbox (`run_python_sandbox`) provides isolated execution for Python scripts with resource limits and automatic artifact management.

## Basic Usage

### Simple Calculation
```python
code = """
import math

# Calculate some statistics
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
mean = sum(data) / len(data)
variance = sum((x - mean) ** 2 for x in data) / len(data)
std_dev = math.sqrt(variance)

print(f"Mean: {mean}")
print(f"Variance: {variance}")
print(f"Std Dev: {std_dev}")
"""
```

### Data Processing (with pandas)
```python
code = """
import pandas as pd

# Create sample data
data = {
    'name': ['Alice', 'Bob', 'Charlie', 'David'],
    'age': [25, 30, 35, 40],
    'salary': [50000, 60000, 70000, 80000]
}

df = pd.DataFrame(data)
print(df)
print(f"\\nAverage salary: ${df['salary'].mean():.2f}")
print(f"Age range: {df['age'].min()} - {df['age'].max()}")
"""
```

### Creating Visualizations
```python
code = """
import matplotlib.pyplot as plt
import numpy as np

# Generate data
x = np.linspace(0, 2 * np.pi, 100)
y1 = np.sin(x)
y2 = np.cos(x)

# Create plot
plt.figure(figsize=(10, 6))
plt.plot(x, y1, label='sin(x)', linewidth=2)
plt.plot(x, y2, label='cos(x)', linewidth=2)
plt.xlabel('x')
plt.ylabel('y')
plt.title('Sine and Cosine Functions')
plt.legend()
plt.grid(True, alpha=0.3)

# Plot will be auto-saved to artifacts/plot_1.png
print("Plot created and saved to artifacts")
"""
```

### Statistical Analysis
```python
code = """
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Generate sample data
np.random.seed(42)
data = np.random.normal(100, 15, 1000)

# Statistical analysis
print(f"Mean: {np.mean(data):.2f}")
print(f"Median: {np.median(data):.2f}")
print(f"Std Dev: {np.std(data):.2f}")
print(f"Min: {np.min(data):.2f}")
print(f"Max: {np.max(data):.2f}")

# Create histogram
plt.figure(figsize=(10, 6))
plt.hist(data, bins=30, edgecolor='black', alpha=0.7)
plt.xlabel('Value')
plt.ylabel('Frequency')
plt.title('Distribution of Random Data')
plt.axvline(np.mean(data), color='red', linestyle='--', label=f'Mean: {np.mean(data):.2f}')
plt.legend()

# Will be saved as artifacts/plot_1.png
"""
```

## Advanced Features

### Multiple Plots
```python
code = """
import matplotlib.pyplot as plt
import numpy as np

# Create multiple figures
fig1 = plt.figure(figsize=(8, 6))
plt.plot([1, 2, 3, 4], [1, 4, 9, 16])
plt.title('Figure 1: Quadratic')

fig2 = plt.figure(figsize=(8, 6))
plt.plot([1, 2, 3, 4], [1, 8, 27, 64])
plt.title('Figure 2: Cubic')

# All figures will be saved:
# - artifacts/plot_1.png
# - artifacts/plot_2.png
print("Created 2 plots")
"""
```

### Data Export
```python
code = """
import pandas as pd
import json
import os

# Create and process data
data = {'x': [1, 2, 3, 4, 5], 'y': [2, 4, 6, 8, 10]}
df = pd.DataFrame(data)

# Export to CSV
artifacts_dir = os.path.join(os.getcwd(), 'artifacts')
os.makedirs(artifacts_dir, exist_ok=True)
df.to_csv(os.path.join(artifacts_dir, 'results.csv'), index=False)

# Export to JSON
results = {
    'mean_x': df['x'].mean(),
    'mean_y': df['y'].mean(),
    'correlation': df['x'].corr(df['y'])
}
with open(os.path.join(artifacts_dir, 'summary.json'), 'w') as f:
    json.dump(results, f, indent=2)

print("Data exported to artifacts/")
"""
```

### Seaborn Visualizations
```python
code = """
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Create sample data
np.random.seed(42)
data = pd.DataFrame({
    'x': np.random.normal(0, 1, 100),
    'y': np.random.normal(0, 1, 100),
    'category': np.random.choice(['A', 'B', 'C'], 100)
})

# Create seaborn plot
plt.figure(figsize=(10, 6))
sns.scatterplot(data=data, x='x', y='y', hue='category', style='category', s=100)
plt.title('Scatter Plot with Categories')

print("Seaborn plot created")
"""
```

## Configuration Examples

### Custom Timeout
```python
# Allow 60 seconds for long-running analysis
result = tool.execute(code=analysis_code, timeout=60)
```

### Disable Network (Default)
```python
# Network is disabled by default via SANDBOX_DISABLE_NETWORK=1
# Scripts attempting network access will get RuntimeError
```

### Using File Path
```python
# Execute an existing Python script
result = tool.execute(file_path="./my_analysis.py")
```

### Skip Artifact Collection
```python
# For performance when artifacts aren't needed
result = tool.execute(code=code, return_artifacts=False)
```

## Resource Limits

The sandbox enforces limits to prevent runaway processes:

- **CPU Time:** `SANDBOX_MAX_CPU_SEC` (default: 20s)
- **Memory:** `SANDBOX_MAX_MEM_MB` (default: 1024MB)
- **File Size:** `SANDBOX_MAX_FSIZE_MB` (default: 50MB)
- **Timeout:** `SANDBOX_TIMEOUT` (default: 30s)

Example of handling timeout:
```python
code = """
import time
# This will timeout after 5 seconds
time.sleep(10)
"""

result = tool.execute(code=code, timeout=5)
# Result will show: timed_out=True, exit_code: None
```

## Artifacts

All generated files in the `artifacts/` directory are automatically tracked:

Supported artifact types:
- `.png`, `.svg` - Images (matplotlib plots)
- `.html` - HTML reports
- `.csv` - Data files
- `.json` - JSON data

Artifacts are listed in the output and stored in:
```
{SANDBOX_PATH}/runs/{run_id}/artifacts/
```

Example manifest.json:
```json
{
  "run_id": "a1b2c3d4-...",
  "run_dir": "/path/to/sandbox_runs/runs/a1b2c3d4-...",
  "exit_code": 0,
  "timed_out": false,
  "artifacts": [
    {
      "path": "/path/to/artifacts/plot_1.png",
      "size": 45678
    }
  ]
}
```

## Security Notes

1. **Process Isolation:** Each run executes in a separate process with resource limits
2. **Network Disabled:** By default, network access is blocked via socket monkeypatch
3. **Environment Sanitization:** Minimal environment variables, isolated HOME directory
4. **Timeout Enforcement:** Process group killed on timeout to prevent orphans
5. **File System:** Runs in isolated directory, but can still read host files (use caution)

## Troubleshooting

### ModuleNotFoundError
If you see errors about missing modules (pandas, numpy, matplotlib):

1. Run the setup script: `./setup_sandbox.sh`
2. Configure in `.env`: `SANDBOX_PYTHON=./sandbox_venv/bin/python`

### Timeout Issues
For compute-intensive tasks, increase timeout:
```bash
# In .env
SANDBOX_TIMEOUT=60
SANDBOX_MAX_CPU_SEC=45
```

### Memory Errors
For large datasets, increase memory limit:
```bash
# In .env
SANDBOX_MAX_MEM_MB=2048
```

### Network Required
To enable network access (use with caution):
```bash
# In .env
SANDBOX_DISABLE_NETWORK=0
```
