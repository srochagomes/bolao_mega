#!/bin/bash

# Build script for Mega-Sena Lottery Generation System
# Builds both backend and frontend

set -e

echo "========================================="
echo "Building Mega-Sena Generation System"
echo "========================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Build Backend
echo -e "\n${BLUE}Building Backend...${NC}"
cd backend

if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# Verify virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "ERROR: Virtual environment not activated!"
    exit 1
fi

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Verify pip installed packages correctly
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies from requirements.txt!"
    exit 1
fi

# Verify critical dependencies
echo "Verifying critical dependencies..."
if python3 -c "import openpyxl; print('✅ openpyxl installed successfully')" 2>/dev/null; then
    echo "✅ openpyxl installed successfully"
else
    echo "ERROR: openpyxl installation failed!"
    echo "Attempting to reinstall openpyxl..."
    pip install --upgrade openpyxl || {
        echo "ERROR: Failed to install openpyxl!"
        exit 1
    }
    # Verify again
    python3 -c "import openpyxl; print('✅ openpyxl installed successfully')" || {
        echo "ERROR: openpyxl still not working after reinstall!"
        exit 1
    }
fi

echo -n "Checking ray (optional, for parallel Excel generation)... "
python3 -c "import ray; print('✅ ray installed successfully')" || {
    echo "⚠️  ray not installed (optional - parallel Excel generation will use sequential mode)"
}

echo -e "${GREEN}Backend dependencies installed successfully${NC}"
cd ..

# Build Frontend
echo -e "\n${BLUE}Building Frontend...${NC}"
cd frontend

echo "Installing Node.js dependencies..."
npm install

echo "Building Next.js application..."
npm run build

echo -e "${GREEN}Frontend built successfully${NC}"
cd ..

echo -e "\n${GREEN}========================================="
echo "Build completed successfully!"
echo "=========================================${NC}"


