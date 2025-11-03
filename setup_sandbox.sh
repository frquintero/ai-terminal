#!/bin/bash
# Setup script for Python sandbox environment
# This creates a dedicated virtual environment with data science libraries

set -e

VENV_DIR="${SANDBOX_VENV_PATH:-./sandbox_venv}"
PYTHON_BIN="${PYTHON:-python3}"

echo "=== AI Terminal Python Sandbox Setup ==="
echo "Creating virtual environment at: $VENV_DIR"

# Create virtual environment
$PYTHON_BIN -m venv "$VENV_DIR"

# Activate and install packages
source "$VENV_DIR/bin/activate"

echo "Installing data science libraries..."
pip install --upgrade pip
pip install --no-cache-dir \
    pandas \
    numpy \
    matplotlib \
    scipy \
    seaborn \
    plotly

echo ""
echo "✓ Sandbox environment created successfully!"
echo ""
echo "To use this sandbox environment, add to your .env file:"
echo "SANDBOX_PYTHON=$VENV_DIR/bin/python"
echo ""
echo "Installed packages:"
pip list | grep -E "(pandas|numpy|matplotlib|scipy|seaborn|plotly)"
