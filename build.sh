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

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Verify critical dependencies
echo "Verifying critical dependencies..."
python3 -c "import reportlab; print('reportlab installed successfully')" || {
    echo "ERROR: reportlab installation failed!"
    exit 1
}
python3 -c "import openpyxl; print('openpyxl installed successfully')" || {
    echo "ERROR: openpyxl installation failed!"
    exit 1
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

