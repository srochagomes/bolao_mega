#!/bin/bash

# Build script for API Backend Only
# Installs Python dependencies and verifies installation

set -e

echo "========================================="
echo "Building Mega-Sena Generation API"
echo "========================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "\n${BLUE}Building Backend API...${NC}"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# Verify virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${RED}❌ Virtual environment not activated!${NC}"
    exit 1
fi

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing Python dependencies..."
pip install -r requirements.txt

# Verify pip installed packages correctly
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to install dependencies from requirements.txt!${NC}"
    exit 1
fi

# Verify critical dependencies
echo -e "\n${BLUE}Verifying critical dependencies...${NC}"

echo -n "Checking fastapi... "
python3 -c "import fastapi; print('✅ fastapi installed successfully')" || {
    echo -e "${RED}❌ fastapi installation failed!${NC}"
    exit 1
}

echo -n "Checking uvicorn... "
python3 -c "import uvicorn; print('✅ uvicorn installed successfully')" || {
    echo -e "${RED}❌ uvicorn installation failed!${NC}"
    exit 1
}

echo -n "Checking pydantic... "
python3 -c "import pydantic; print('✅ pydantic installed successfully')" || {
    echo -e "${RED}❌ pydantic installation failed!${NC}"
    exit 1
}

echo -n "Checking numpy... "
python3 -c "import numpy; print('✅ numpy installed successfully')" || {
    echo -e "${RED}❌ numpy installation failed!${NC}"
    exit 1
}

echo -n "Checking pandas... "
python3 -c "import pandas; print('✅ pandas installed successfully')" || {
    echo -e "${RED}❌ pandas installation failed!${NC}"
    exit 1
}

echo -n "Checking openpyxl... "
if python3 -c "import openpyxl; print('✅ openpyxl installed successfully')" 2>/dev/null; then
    echo "✅ openpyxl installed successfully"
else
    echo -e "${RED}❌ openpyxl installation failed!${NC}"
    echo "Attempting to reinstall openpyxl..."
    pip install --upgrade openpyxl || {
        echo -e "${RED}❌ Failed to install openpyxl!${NC}"
        exit 1
    }
    # Verify again
    python3 -c "import openpyxl; print('✅ openpyxl installed successfully')" || {
        echo -e "${RED}❌ openpyxl still not working after reinstall!${NC}"
        exit 1
    }
fi

echo -n "Checking ray (optional, for parallel Excel generation)... "
python3 -c "import ray; print('✅ ray installed successfully')" || {
    echo -e "${BLUE}⚠️  ray not installed (optional - parallel Excel generation will use sequential mode)${NC}"
}

# reportlab removed - not used in the application (using weasyprint instead)

echo -n "Checking weasyprint... "
python3 -c "import weasyprint; print('✅ weasyprint installed successfully')" || {
    echo -e "${RED}❌ weasyprint installation failed!${NC}"
    exit 1
}

# Verify API can be imported
echo -e "\n${BLUE}Verifying API structure...${NC}"
python3 -c "from app.main import app; print('✅ API application can be imported successfully')" || {
    echo -e "${RED}❌ API application import failed!${NC}"
    exit 1
}

echo -e "\n${GREEN}========================================="
echo "API build completed successfully!"
echo "=========================================${NC}"
echo ""
echo "To start the API server:"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "Or use the start script:"
echo "  ./start-api.sh"
echo ""
