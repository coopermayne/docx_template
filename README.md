# Legal Discovery RFP Response Generator

A Python/Flask backend with Claude AI integration for analyzing legal discovery requests (Requests for Production) and generating formatted Word document responses.

## Features

- 📄 Upload and parse RFP PDFs with automatic case info extraction
- 🤖 AI-powered analysis of discovery requests using Claude
- 📋 Manage responsive documents with Bates number detection
- ⚖️ Customizable objections library stored in Supabase
- 📝 Generate professional Word document responses from templates
- 👥 Multi-user support with user profiles
- 📁 Custom document templates per user

## Prerequisites

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** | API key for Claude AI features (analysis, case info extraction) |
| `SUPABASE_URL` | **Yes** | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | **Yes** | Supabase anonymous/public key |
| `CLAUDE_MODEL` | No | Claude model to use (default: `claude-sonnet-4-20250514`) |
| `PORT` | No | Server port (default: 5000, Render uses 10000) |

### Required External Services

#### 1. Anthropic API (Claude)

Used for:
- Analyzing RFP requests and suggesting responses
- Extracting case information from PDF first pages
- Composing response text

**Setup:**
1. Create account at [console.anthropic.com](https://console.anthropic.com)
2. Generate an API key
3. Set `ANTHROPIC_API_KEY` environment variable

#### 2. Supabase

Used for:
- Storing objections library (`objections` table)
- User profiles (`users` table)
- Document templates (`templates` table + `templates` storage bucket)

**Setup:**
1. Create project at [supabase.com](https://supabase.com)
2. Run the schema from `supabase_schema.sql`
3. Create a storage bucket named `templates` (private)
4. Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` environment variables

**Database Schema:**
```sql
-- See supabase_schema.sql for full schema
-- Key tables:
--   objections: id, short_form, full_form, category, user_id
--   users: id, bar_number, name, email, icon
--   templates: id, name, user_id, storage_path, created_at
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/coopermayne/docx_template.git
cd docx_template
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
export ANTHROPIC_API_KEY="your-api-key"
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_ANON_KEY="your-anon-key"
```

## Running the Application

### Development
```bash
python app.py
```
The API will be available at `http://localhost:5000`

### Production
```bash
gunicorn app:app
```

## API Overview

### Session Management
- `POST /api/session/create` - Create new session
- `GET /api/session/<id>` - Get session data
- `DELETE /api/session/<id>` - Delete session

### RFP Processing
- `POST /api/rfp/upload` - Upload RFP PDF
- `GET /api/rfp/<id>/case-info` - Get extracted case info
- `PUT /api/rfp/<id>/case-info` - Update case info

### Document Management
- `POST /api/documents/upload` - Upload responsive documents
- `GET /api/documents/<session_id>` - List documents
- `DELETE /api/documents/<session_id>/<doc_id>` - Remove document

### Analysis & Generation
- `POST /api/analyze/<session_id>` - Run AI analysis on requests
- `POST /api/generate/<session_id>` - Generate Word response document

### Objections (Supabase)
- `GET /api/objections` - List all objections
- `POST /api/objections` - Create objection
- `PUT /api/objections/<id>` - Update objection
- `DELETE /api/objections/<id>` - Delete objection

### Users (Supabase)
- `GET /api/users` - List all users
- `POST /api/users` - Create user
- `PUT /api/users/<id>` - Update user

### Templates (Supabase)
- `GET /api/templates` - List templates
- `POST /api/templates` - Upload template
- `DELETE /api/templates/<id>` - Delete template

## Architecture

```
Frontend (Alpine.js SPA)
         │
         ▼
Flask API (app.py + api/ blueprints)
         │
    ┌────┴────┐
    ▼         ▼
Services   Models
    │
    ├── claude_service.py     # AI integration
    ├── pdf_parser.py         # PDF text extraction
    ├── document_generator.py # Word doc generation
    ├── session_store.py      # JSON file persistence
    ├── bates_detector.py     # Bates number extraction
    └── supabase_service.py   # Supabase REST client
```

## Data Flow

1. **Session Creation** - Initialize new RFP response session
2. **RFP Upload** - PDF parsed, requests extracted, case info auto-extracted via Claude
3. **Document Upload** - Responsive documents added, Bates numbers detected from filenames
4. **Analysis** - Claude analyzes each request, suggests responses and objections
5. **Generation** - Word document created from template with all response data

## Testing

```bash
python -m unittest test_app.py -v
```

## Deployment

Configured for Render deployment via `render.yaml`.

Required Render environment variables:
- `ANTHROPIC_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

## Project Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for planned features and development roadmap.

## License

MIT
