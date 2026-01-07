# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Legal discovery RFP (Request for Production) response generation tool. Python/Flask backend with Claude AI integration for analyzing discovery requests and generating Word document responses.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (port 5000)
python app.py

# Run production server
gunicorn app:app

# Run tests
python -m unittest test_app.py -v
```

## Environment Variables

- `ANTHROPIC_API_KEY` - Required for Claude AI features (analysis, extraction)
- `CLAUDE_MODEL` - Model name (default: claude-sonnet-4-20250514)
- `PORT` - Server port (default: 5000, Render uses 10000)
- `SUPABASE_URL` - Supabase project URL (required for objections)
- `SUPABASE_ANON_KEY` - Supabase anonymous key (required for objections)

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
```

### Key Data Flow

1. **Session Creation** - POST /api/session/create
2. **RFP Upload** - POST /api/rfp/upload (PDF parsed, case info extracted via Claude)
3. **Document Upload** - POST /api/documents/upload (Bates numbers detected from filenames)
4. **Analysis** - POST /api/analyze/{session_id} (Claude analyzes each request)
5. **Generation** - POST /api/generate/{session_id} (Creates DOCX response)

### Services Layer (`/services`)

- **claude_service.py** - All Claude API calls using tool_choice for structured outputs
- **pdf_parser.py** - PDF text extraction (PyPDF2 primary, pdfplumber fallback)
- **document_generator.py** - Word generation via docxtpl templates, python-docx fallback
- **session_store.py** - JSON file persistence in ./data/sessions/
- **bates_detector.py** - Extract Bates ranges from document filenames
- **supabase_service.py** - Supabase REST API client for cloud storage

### API Blueprints (`/api`)

- session.py - Session CRUD
- rfp.py - RFP upload/parsing/case info extraction
- documents.py - Responsive document management
- analyze.py - Trigger Claude analysis
- generate.py - Generate DOCX response
- objections.py - Objections CRUD (Supabase)
- users.py - Users CRUD (Supabase)
- templates.py - Templates CRUD (Supabase + Storage)
- motion_opposition.py - Motion opposition document generation

## Key Patterns

### Claude Integration
Uses `tool_choice` constraint for structured outputs. Three tools defined:
- `submit_analysis` - RFP request analysis
- `submit_case_info` - Case header extraction from first page
- `submit_response` - Response composition

Falls back to keyword-based analysis when Claude unavailable.

**Future Optimization - Prompt Caching:**
For very large RFPs (100+ requests) with many uploaded documents, Anthropic's prompt caching could reduce costs by caching the repeated system content (objections list, documents list, instructions) across chunk API calls. Requirements:
- Minimum 1024 tokens of cacheable content (Sonnet)
- Multiple chunks needed to see benefit (cache created on first call, read on subsequent)
- See: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Implementation would involve: adding `system` parameter to `_call_claude_api()` with `cache_control: {"type": "ephemeral"}` on content blocks

### Persistence
- Sessions: JSON files in ./data/sessions/{session_id}.json
- Uploads: ./data/uploads/{session_id}/
- Both directories auto-created, in .gitignore

### Document Generation
Primary: docxtpl with Jinja2 templates in ./templates/word/rfp_template.docx
Fallback: Programmatic python-docx generation

### Objections System
Stored in Supabase `objections` table. Requires `SUPABASE_URL` and `SUPABASE_ANON_KEY` env vars.

### Users System
Stored in Supabase `users` table (bar_number, name, email, icon).
Frontend session stored in localStorage - users select from dropdown, no auth required.

### Templates System
Document templates (.docx) stored in Supabase Storage bucket `templates`.
Metadata tracked in `templates` table. See `supabase_schema.sql` for setup.

**Supabase Storage Setup:**
1. Go to Supabase Dashboard > Storage
2. Create a new bucket named `templates`
3. Set bucket to private (not public)
4. Configure RLS policies to allow authenticated access
