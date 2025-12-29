#!/bin/bash

# Frontend Startup Script
# Starts the Next.js frontend application

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/frontend"

echo "========================================="
echo "Starting Mega-Sena Frontend"
echo "========================================="

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Node modules not found. Installing dependencies..."
    npm install
fi

# Check for production mode
if [ "$1" = "prod" ] || [ "$1" = "production" ]; then
    echo "Starting in production mode..."
    echo "Building application..."
    npm run build
    echo ""
    echo "Starting production server on http://localhost:3000"
    echo "Press Ctrl+C to stop the server"
    echo "========================================="
    npm start
else
    echo "Starting in development mode..."
    echo ""
    echo "Frontend will be available at http://localhost:3000"
    echo "Press Ctrl+C to stop the server"
    echo "========================================="
    npm run dev
fi

