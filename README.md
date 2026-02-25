# Resume Engine MVP

Upload, parse, and search resumes using AI.

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env         # Add your ANTHROPIC_API_KEY
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Tech Stack
- **Backend**: Python + FastAPI
- **Parsing**: PyMuPDF (PDF) + python-docx (DOCX)
- **AI**: Claude claude-haiku-4-5 via Anthropic API
- **Database**: SQLite + FTS5 full-text search
- **Frontend**: React + Vite + Tailwind CSS
