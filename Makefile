.PHONY: help build build-backend build-frontend start-api start-frontend install clean

help:
	@echo "Mega-Sena Lottery Generation System - Makefile"
	@echo ""
	@echo "Available commands:"
	@echo "  make build           - Build both backend and frontend"
	@echo "  make build-backend   - Build backend only"
	@echo "  make build-frontend  - Build frontend only"
	@echo "  make start-api       - Start the FastAPI backend server"
	@echo "  make start-frontend  - Start the Next.js frontend (development)"
	@echo "  make install         - Install all dependencies"
	@echo "  make clean           - Clean build artifacts"
	@echo ""

build: build-backend build-frontend

build-backend:
	@echo "Building backend..."
	@cd backend && \
	if [ ! -d "venv" ]; then \
		python3 -m venv venv; \
	fi && \
	. venv/bin/activate && \
	pip install --upgrade pip && \
	pip install -r requirements.txt

build-frontend:
	@echo "Building frontend..."
	@cd frontend && \
	npm install && \
	npm run build

install: build-backend
	@cd frontend && npm install

start-api:
	@./start-api.sh

start-frontend:
	@./start-frontend.sh

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf backend/venv
	@rm -rf backend/__pycache__
	@rm -rf backend/**/__pycache__
	@rm -rf frontend/.next
	@rm -rf frontend/node_modules
	@echo "Clean completed"

