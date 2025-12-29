# Mega-Sena Lottery Number Generation System

A production-grade lottery number generation system that uses historical data and statistical analysis to generate organized combinations. **This system does not predict results or increase winning probability** - it only organizes combinations using statistical insights.

## ⚠️ Important Disclaimer

**This system does not increase the probability of winning.** It provides statistical organization and rule-based combination generation only. Lottery outcomes are random and cannot be predicted. Use this tool for entertainment and organizational purposes only.

## System Architecture

### Backend (Python/FastAPI)
- **Internal Historical Data**: Ingests and manages Mega-Sena historical data (not user-facing)
- **Statistical Analysis Engine**: Performs frequency analysis, odd/even distribution, repetition patterns
- **Generation Engine**: Rule-based game generation with user-defined constraints
- **Async Job Processing**: In-memory job store with TTL
- **Excel Generation**: Creates validated Excel files with multiple sheets
- **PDF/HTML Generation**: Generates lottery tickets for printing

### Frontend (Next.js)
- Single Page Application with parameter input form
- Real-time job status tracking
- Excel file download and management
- File checking against drawn numbers
- PDF/HTML ticket generation for printing

## Features

- ✅ User-driven generation (only when explicitly requested)
- ✅ Automatic statistical analysis (frequency, odd/even, sequences based on historical data)
- ✅ Rule-based constraints (repetition, fixed numbers)
- ✅ Excel output with validation and audit sheets
- ✅ Async job processing with status tracking
- ✅ In-memory processing (no database)
- ✅ PDF/HTML ticket generation for lottery machines
- ✅ File checking against drawn numbers
- ✅ Dynamic pricing based on number of dezenas (6-17)

## Prerequisites

- Python 3.8+
- Node.js 18+
- npm or yarn

## Quick Start

### Option 1: Using Scripts

1. **Build the project:**
   ```bash
   ./build.sh
   ```

2. **Start the API (in one terminal):**
   ```bash
   ./start-api.sh
   ```

3. **Start the Frontend (in another terminal):**
   ```bash
   ./start-frontend.sh
   ```

### Option 2: Using Makefile

1. **Build everything:**
   ```bash
   make build
   ```

2. **Start services:**
   ```bash
   make start-api      # Terminal 1
   make start-frontend # Terminal 2
   ```

### Option 3: Manual Setup

#### Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Frontend Setup

```bash
cd frontend
npm install
npm run dev  # Development mode
# or
npm run build && npm start  # Production mode
```

## Usage

1. Open http://localhost:3000 in your browser
2. Fill in the generation parameters:
   - **Mode**: By Budget or By Quantity
   - **Budget** (BRL) or **Quantity** of games
   - **Numbers per game** (6-17 dezenas)
   - **Max Repetition** (optional): Maximum repeated numbers between games
   - **Fixed Numbers** (optional): Numbers that must appear in all games
3. Click "Generate Games"
4. Monitor job status in real-time
5. Download the Excel file when completed
6. Generate PDF/HTML tickets for printing (from file list)

## Excel File Structure

The generated Excel file contains three sheets:

1. **Manual Input**: Editable cells for entering drawn numbers to check against generated games
2. **Generated Games**: All generated games with match highlighting and formulas
3. **Rules & Summary**: Complete audit of all parameters and disclaimer

## API Endpoints

- `POST /api/v1/generate` - Create generation job
- `GET /api/v1/jobs/{process_id}/status` - Get job status
- `GET /api/v1/jobs/{process_id}/download` - Download Excel file
- `DELETE /api/v1/jobs/{process_id}` - Cancel job
- `GET /api/v1/files` - List saved files
- `GET /api/v1/files/{process_id}/download` - Download saved file
- `GET /api/v1/files/{process_id}/html` - Generate HTML tickets for printing
- `POST /api/v1/files/check` - Check Excel file against drawn numbers
- `GET /api/v1/historical/status` - Get historical data status
- `POST /api/v1/historical/refresh` - Refresh historical data

API documentation available at: http://localhost:8000/docs

## Configuration

Backend configuration is in `backend/app/core/config.py`:
- `MAX_CONCURRENT_JOBS`: Maximum concurrent jobs (default: 3)
- `JOB_TTL_SECONDS`: Job expiration time (default: 1800s / 30min)
- `MAX_GAMES_PER_REQUEST`: Maximum games per request (default: 1000)
- `MAX_PROCESSING_TIME_SECONDS`: Maximum processing time per job (default: 300s / 5min)
- `MEGA_SENA_PRICES`: Dictionary with prices for 6-17 dezenas

## Pricing

The system uses official Mega-Sena pricing:
- 6 dezenas: R$ 6,00
- 7 dezenas: R$ 42,00
- 8 dezenas: R$ 168,00
- 9 dezenas: R$ 504,00
- 10 dezenas: R$ 1.260,00
- 11 dezenas: R$ 2.772,00
- 12 dezenas: R$ 5.544,00
- 13 dezenas: R$ 10.296,00
- 14 dezenas: R$ 18.018,00
- 15 dezenas: R$ 30.030,00
- 16 dezenas: R$ 48.048,00
- 17 dezenas: R$ 74.256,00

## Project Structure

```
bolao-loteria/
├── backend/
│   ├── app/
│   │   ├── api/          # API endpoints
│   │   ├── core/         # Configuration
│   │   ├── models/       # Pydantic models
│   │   ├── services/     # Business logic
│   │   └── main.py       # FastAPI app
│   ├── storage/          # Generated files (gitignored)
│   │   ├── excel_files/  # Generated Excel files
│   │   └── metadata/     # File metadata
│   ├── tests/            # Unit tests
│   ├── requirements.txt
│   └── venv/             # Virtual environment (gitignored)
├── frontend/
│   ├── app/              # Next.js app directory
│   ├── components/       # React components
│   ├── lib/              # Utilities and API client
│   ├── public/           # Static assets
│   ├── package.json
│   └── node_modules/     # Dependencies (gitignored)
├── build.sh              # Build script
├── start-api.sh          # API startup script
├── start-frontend.sh     # Frontend startup script
├── Makefile              # Make commands
├── .gitignore            # Git ignore rules
└── README.md
```

## Development

### Backend Development

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

### Frontend Development

```bash
cd frontend
npm run dev
```

### Running Tests

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

## Statistical Analysis

The system automatically applies statistical rules based on historical Mega-Sena data:

- **Frequency Analysis**: Balances high, medium, and low frequency numbers
- **Odd/Even Distribution**: Maintains historical odd/even patterns
- **Sequential Patterns**: Avoids unrealistic sequential patterns
- **Recent Numbers**: Considers numbers from recent draws

All statistical rules are applied automatically - no manual configuration needed.

## File Management

Generated Excel files are saved to `backend/storage/excel_files/` with metadata in `backend/storage/metadata/`. Files can be:
- Downloaded as Excel
- Used to generate PDF/HTML tickets for printing
- Checked against drawn numbers

## Security & Limits

- Rate limiting per session/user
- Hard limits on maximum games and processing time
- Input validation on all parameters
- No raw historical data exposure to users
- Timeout protection for long-running jobs

## Troubleshooting

### Backend won't start
- Check if Python 3.8+ is installed: `python3 --version`
- Ensure virtual environment is activated
- Install dependencies: `pip install -r requirements.txt`

### Frontend won't start
- Check if Node.js 18+ is installed: `node --version`
- Install dependencies: `npm install`
- Check if port 3000 is available

### Generation is slow
- Reduce the number of games requested
- Check if fixed numbers allow enough combinations
- Verify historical data is loaded (check `/api/v1/historical/status`)

### Jobs timeout
- Reduce the number of games per request
- Check server resources
- Increase `MAX_PROCESSING_TIME_SECONDS` in config if needed

## License

This project is for educational and organizational purposes only.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Submit a pull request

## Support

For issues and questions, please open an issue on the repository.
