#!/usr/bin/env bash

echo "🚀 Initializing Test Environment..."

# Check if the virtual environment directory already exists
if [ ! -d ".venv" ]; then
    echo "Establishing a Python virtual environment first..."
    uv venv

    echo "Installing the required language version internally..."
    uv python pin 3.12
    uv sync
else
    echo "Virtual environment already exists. Skipping creation."
fi

# Activate the isolated environment
source .venv/bin/activate

# Execute the test suite using the module flag for path resolution
echo "🧪 Running Pytest..."
python -m pytest -v