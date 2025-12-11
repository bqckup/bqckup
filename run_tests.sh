#!/bin/bash

# Bqckup Test Runner Script

echo "🧪 Running Bqckup Unit Tests..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run unit tests
echo "Running unit tests..."
python -m pytest tests/unit/ -v

# Run integration tests
echo "Running integration tests..."
python -m pytest tests/integration/ -v

# Run all tests with coverage
echo "Running all tests with coverage..."
python -m pytest tests/ --cov=. --cov-report=term-missing --cov-report=html

echo "✅ Tests completed! Check htmlcov/index.html for detailed coverage report."
