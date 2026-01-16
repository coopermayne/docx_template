# New Gen Feature - Implementation Plan

## Overview
A new tab called "New Gen" that allows users to:
1. Upload a PDF (optional) for AI-assisted variable extraction
2. Select a template from the template library
3. Review/edit AI-suggested values for template variables
4. Generate the final document

## User Flow

```
┌─────────────────────────────────────────────────────────────┐
│  NEW GEN TAB                                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────┐  ┌────────────────────────────┐   │
│  │  Drop PDF here       │  │  Select Template           │   │
│  │  (optional)          │  │  [Filter: ________]        │   │
│  │                      │  │  ○ template1.docx          │   │
│  │  [filename.pdf ✓]    │  │  ● template2.docx ← selected│  │
│  └──────────────────────┘  │  ○ template3.docx          │   │
│                            └────────────────────────────┘   │
│                                                             │
│  [ Analyze & Fill Variables ]  ← enabled when template      │
│                                   selected                  │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│  (After clicking Analyze, or if skipping PDF)               │
│                                                             │
│  Template Variables:                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  court_name:     [Superior Court of California___]  │   │
│  │  case_number:    [2:24-cv-01234________________]    │   │
│  │  plaintiff:      [John Smith____________________]   │   │
│  │  defendant:      [ACME Corp_____________________]   │   │
│  │  ...                                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [ Generate Document ]                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Technical Implementation

### Files to Create

#### 1. `api/new_gen.py` - New Blueprint

**Endpoints:**

```python
POST /api/new-gen/analyze
```
- **Input:** multipart form with:
  - `template_id` (required) - ID of selected template
  - `pdf` (optional) - PDF file for context
  - `user_name` (required) - logged-in user's name
  - `user_bar` (required) - bar number
  - `user_email` (required) - email
- **Process:**
  1. Download template from Supabase Storage
  2. Extract template variables using docxtpl
  3. If PDF provided, extract first 2 pages of text
  4. Call Claude with template content + PDF text + user info
  5. Return JSON with variable values
- **Output:**
  ```json
  {
    "variables": ["court_name", "case_number", ...],
    "values": {
      "court_name": "Superior Court of California",
      "case_number": "2:24-cv-01234",
      "some_field": null
    }
  }
  ```

```python
POST /api/new-gen/variables
```
- **Input:** `template_id`
- **Process:** Extract variables from template without AI
- **Output:** `{ "variables": ["var1", "var2", ...] }`
- **Use case:** When user skips PDF upload, just get variable list

```python
POST /api/new-gen/generate
```
- **Input:** JSON body with:
  - `template_id` (required)
  - `values` (required) - dict of variable name → value
- **Process:**
  1. Download template from Supabase
  2. Render with docxtpl using provided values
  3. Return generated .docx file
- **Output:** Binary .docx file download

---

#### 2. `services/template_extractor.py` - Template Variable Extraction

```python
def extract_variables(docx_path: str) -> List[str]:
    """Extract all Jinja2 variable names from a .docx template."""

def extract_template_content(docx_path: str) -> str:
    """Extract the text content of a template for AI context."""
```

---

#### 3. `services/new_gen_ai.py` - AI Service for New Gen

```python
def analyze_for_template(
    template_content: str,
    template_variables: List[str],
    pdf_text: str,
    user_info: dict
) -> Dict[str, Optional[str]]:
    """
    Use Claude to extract values for template variables.

    Returns dict mapping variable names to values (or None if unknown).
    """
```

**Claude Prompt Strategy:**
- Send full template text so AI understands context
- Send list of variable names to fill
- Send first 2 pages of PDF for source content
- Send user info (name, bar, email) for attorney fields
- Request structured JSON response with tool_choice

---

### Files to Modify

#### 4. `app.py`
- Register new blueprint: `from api.new_gen import new_gen_bp`

#### 5. `static/js/api.js`
- Add new API functions:
  ```javascript
  async analyzeForTemplate(templateId, pdfFile, userInfo) { ... }
  async getTemplateVariables(templateId) { ... }
  async generateFromTemplate(templateId, values) { ... }
  ```

#### 6. `templates/index.html`
- Add "New Gen" tab to navigation
- Add new page section with:
  - PDF dropzone (optional)
  - Template list with filter
  - Analyze button
  - Variables form (dynamic)
  - Generate button
  - Loading modal

---

## Implementation Steps

### Phase 1: Backend Foundation
1. Create `services/template_extractor.py`
   - `extract_variables()` using docxtpl
   - `extract_template_content()` for AI context

2. Create `services/new_gen_ai.py`
   - Claude tool definition for structured JSON output
   - `analyze_for_template()` function

3. Create `api/new_gen.py`
   - `/analyze` endpoint
   - `/variables` endpoint
   - `/generate` endpoint

4. Update `app.py` to register blueprint

### Phase 2: Frontend
5. Update `static/js/api.js`
   - Add API client functions

6. Update `templates/index.html`
   - Add navigation tab
   - Add page UI with all components
   - Wire up Alpine.js logic

---

## State Management (Alpine.js)

```javascript
// New Gen state
newGenPdf: null,              // Uploaded PDF file
newGenPdfName: null,          // PDF filename for display
newGenTemplates: [],          // List of templates from API
newGenTemplateFilter: '',     // Filter text for template list
newGenSelectedTemplate: null, // Selected template object
newGenAnalyzing: false,       // Loading state for analyze
newGenVariables: [],          // List of variable names
newGenValues: {},             // Current values for variables
newGenError: null,            // Error message
newGenGenerating: false,      // Loading state for generate
```

---

## Error Handling

1. **Template list fails to load:** Show error, retry button
2. **AI analysis fails:** Show error message, allow retry with same inputs
3. **Generate fails:** Show error message, keep form state so user can retry
4. **PDF parsing fails:** Show error, allow user to continue without PDF

---

## UI Details

### Template List
- Show template name and upload date
- Radio button selection (single select)
- Filter input filters by template name (case-insensitive contains)
- Newest templates first (already sorted by API)

### Variables Form
- All inputs are single-line text fields
- Label is the variable name (formatted: snake_case → Title Case)
- Null values from AI shown as empty fields
- All fields editable

### Buttons
- "Analyze & Fill Variables" - disabled until template selected
- "Generate Document" - disabled until variables form is shown
- "Skip to Manual Entry" - appears if template selected but no PDF, lets user skip AI

---

## File Structure After Implementation

```
api/
  new_gen.py          # NEW - API endpoints
services/
  template_extractor.py  # NEW - Variable extraction
  new_gen_ai.py          # NEW - AI integration
static/js/
  api.js              # MODIFIED - New API functions
templates/
  index.html          # MODIFIED - New tab UI
app.py                # MODIFIED - Register blueprint
```
