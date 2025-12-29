#!/bin/bash

# API Startup Script
# Starts the FastAPI backend server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend"

echo "========================================="
echo "Starting Mega-Sena Generation API"
echo "========================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv venv
    echo "Installing dependencies..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Dependencies not installed. Installing..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

echo ""
echo "Starting FastAPI server on http://localhost:8000"
echo "API documentation: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo "========================================="

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

