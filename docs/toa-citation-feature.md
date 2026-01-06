# Table of Authorities Citation Processing Feature

## Overview

Automatically process legal briefs to:
1. Detect all citations (cases, statutes, rules, treatises)
2. Identify and correct citation errors
3. Insert Word TA (Table of Authorities) field codes for TOA generation

## Problem Statement

Creating a Table of Authorities in Word is tedious and error-prone. Attorneys must:
- Manually mark each citation with TA field codes
- Ensure consistent formatting across long/short forms
- Track Id. references correctly
- Avoid common mistakes (short before long, duplicate longs, etc.)

This feature automates the entire process using AI.

---

## User Workflow

```
1. Upload DOCX brief
          │
2. System strips existing TA codes (clean slate)
          │
3. AI analyzes document, returns:
   - All detected citations grouped by authority
   - Detected errors with proposed fixes
          │
4. User reviews errors in UI
   - Accept/reject/modify each proposed fix
          │
5. System applies confirmed corrections
          │
6. System inserts TA field codes
          │
7. User downloads processed DOCX
          │
8. User generates TOA in Word (Insert → Table of Authorities)
```

---

## Citation Categories

| Category | Code | Examples |
|----------|------|----------|
| Cases | 1 | *Smith v. Jones*, 123 F.3d 456 (9th Cir. 2020) |
| Statutes | 2 | 28 U.S.C. § 1332, Cal. Civ. Code § 1542 |
| Rules | 3 | Fed. R. Civ. P. 12(b)(6), Local Rule 7-3 |
| Treatises | 4 | 5 Witkin, Cal. Procedure (5th ed. 2008) |

---

## Error Detection & Correction

### Error Type 1: Short Cite Before Long Cite

**Problem:** First reference to an authority uses short form instead of full citation.

**Example:**
```
Page 3: "Smith held that..."
Page 7: "In Smith v. Jones, 123 F.3d 456 (9th Cir. 2020), the court..."
```

**Detection:** AI identifies that "Smith" (p.3) refers to the same case as the full citation (p.7), but appears first.

**Proposed Fix Options:**
- Flag for user attention (they may need to manually restructure)
- Note: We mark with TA codes as-is; the TOA will still work, but the brief text may be unclear to readers

---

### Error Type 2: Duplicate Long Citations

**Problem:** Full citation appears multiple times when subsequent references should use short form.

**Example:**
```
Page 3: "Smith v. Jones, 123 F.3d 456 (9th Cir. 2020)"
Page 8: "Smith v. Jones, 123 F.3d 456 (9th Cir. 2020)"  ← Should be "Smith" or "Smith v. Jones"
```

**Detection:** AI identifies multiple instances of identical full citations.

**Proposed Fix:** Convert subsequent full citations to short form.
```
Page 8: "Smith v. Jones, 123 F.3d 456 (9th Cir. 2020)" → "Smith, 123 F.3d at 456" or "Smith"
```

---

### Error Type 3: Missing Id.

**Problem:** Consecutive citations to the same authority should use "Id." but don't.

**Example:**
```
Footnote 5: "Smith v. Jones, 123 F.3d 456, 460 (9th Cir. 2020)."
Footnote 6: "Smith, 123 F.3d at 461."  ← Should be "Id. at 461."
```

**Detection:** AI tracks reading order; when same authority is cited consecutively, flags missing Id.

**Proposed Fix:** Replace with "Id." or "Id. at [pinpoint]"

---

### Error Type 4: Orphaned Id.

**Problem:** "Id." appears but doesn't follow a citation (or follows a string cite).

**Example:**
```
Footnote 10: "See Smith, 123 F.3d at 460; Jones, 456 F.3d at 789."
Footnote 11: "Id. at 461."  ← Ambiguous - which case?
```

**Detection:** AI identifies Id. that follows multiple citations or no citation.

**Proposed Fix:** Expand to explicit short form; user confirms which authority.

---

## Technical Architecture

### New Files

```
services/
  toa_service.py              # Main orchestrator
  toa_xml_utils.py            # TA field XML construction
  toa_text_extractor.py       # Extract text with position mapping

api/
  toa.py                      # API endpoints

docs/
  toa-citation-feature.md     # This file
```

### API Endpoints

#### `POST /api/toa/analyze`

Upload document, receive analysis with detected citations and errors.

**Request:**
```
Content-Type: multipart/form-data
file: <docx file>
```

**Response:**
```json
{
  "session_id": "toa_abc123",
  "authorities": [
    {
      "id": "smith_v_jones",
      "category": 1,
      "long_citation": "Smith v. Jones, 123 F.3d 456 (9th Cir. 2020)",
      "short_form": "Smith",
      "instances": [
        {
          "position_id": "body_p3_r2",
          "text": "Smith v. Jones, 123 F.3d 456 (9th Cir. 2020)",
          "type": "long",
          "location": "Body paragraph 3"
        },
        {
          "position_id": "fn_5_r1",
          "text": "Smith, 123 F.3d at 460",
          "type": "short_pinpoint",
          "location": "Footnote 5"
        }
      ]
    }
  ],
  "errors": [
    {
      "id": "err_1",
      "type": "duplicate_long",
      "authority_id": "smith_v_jones",
      "description": "Full citation appears twice",
      "instances": ["body_p3_r2", "body_p12_r1"],
      "proposed_fix": {
        "action": "convert_to_short",
        "target": "body_p12_r1",
        "new_text": "Smith"
      }
    },
    {
      "id": "err_2",
      "type": "missing_id",
      "authority_id": "smith_v_jones",
      "description": "Consecutive citation should use Id.",
      "instance": "fn_6_r1",
      "proposed_fix": {
        "action": "replace",
        "new_text": "Id. at 461"
      }
    }
  ],
  "statistics": {
    "total_citations": 47,
    "cases": 12,
    "statutes": 8,
    "rules": 3,
    "treatises": 2,
    "errors_found": 5
  }
}
```

#### `POST /api/toa/apply`

Apply confirmed corrections and insert TA codes.

**Request:**
```json
{
  "session_id": "toa_abc123",
  "accepted_fixes": ["err_1", "err_2"],
  "rejected_fixes": ["err_3"],
  "modified_fixes": [
    {
      "id": "err_4",
      "new_text": "Id. at 462"
    }
  ]
}
```

**Response:**
```
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="brief_with_toa_codes.docx"
```

---

## Claude AI Integration

### Tool Definition

```python
{
    "name": "analyze_legal_citations",
    "description": "Analyze a legal document to identify all citations and citation errors",
    "input_schema": {
        "type": "object",
        "properties": {
            "authorities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "category": {"type": "integer", "enum": [1, 2, 3, 4]},
                        "long_citation": {"type": "string"},
                        "short_form": {"type": "string"},
                        "instances": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "position_id": {"type": "string"},
                                    "text_as_written": {"type": "string"},
                                    "type": {"type": "string", "enum": ["long", "short", "short_pinpoint", "id", "id_pinpoint"]}
                                }
                            }
                        }
                    }
                }
            },
            "errors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["short_before_long", "duplicate_long", "missing_id", "orphaned_id"]},
                        "authority_id": {"type": "string"},
                        "position_id": {"type": "string"},
                        "description": {"type": "string"},
                        "proposed_fix": {"type": "string"}
                    }
                }
            }
        }
    }
}
```

### Prompt Strategy

The prompt must:
1. Provide full document text with position markers
2. Explain citation conventions (Bluebook basics)
3. Request reading-order processing for Id. resolution
4. Ask for both detection and error identification

---

## Word TA Field Format

### Field Structure

```xml
<w:r>
  <w:fldChar w:fldCharType="begin"/>
</w:r>
<w:r>
  <w:instrText> TA \l "Smith v. Jones, 123 F.3d 456 (9th Cir. 2020)" \s "Smith" \c 1 </w:instrText>
</w:r>
<w:r>
  <w:fldChar w:fldCharType="separate"/>
</w:r>
<w:r>
  <w:fldChar w:fldCharType="end"/>
</w:r>
```

### Field Parameters

| Parameter | Purpose | Example |
|-----------|---------|---------|
| `\l` | Long citation (appears in TOA) | `\l "Smith v. Jones, 123 F.3d 456 (9th Cir. 2020)"` |
| `\s` | Short form (for matching) | `\s "Smith"` |
| `\c` | Category number | `\c 1` (Cases) |
| `\b` | Bold | Optional formatting |
| `\i` | Italic | Optional formatting |

### Insertion Rules

1. TA field is inserted **immediately after** the citation text
2. Field is hidden text (not visible in normal view)
3. Every instance of a citation (long, short, Id.) gets the same TA field
4. Word compiles TOA by collecting all matching `\l` values

---

## Position Mapping Strategy

The critical challenge: mapping extracted text back to document XML.

### Approach

1. **During extraction:** Build a map of `{position_id: (paragraph_index, run_index)}`
   ```python
   position_map = {
       "body_p3_r2": (paragraph=3, run=2),
       "fn_5_r1": (footnote=5, run=1),
   }
   ```

2. **In extracted text:** Insert markers that AI preserves
   ```
   [body_p3_r2]Smith v. Jones, 123 F.3d 456 (9th Cir. 2020)[/body_p3_r2]
   ```

3. **AI returns:** Position IDs with each detected citation

4. **During insertion:** Look up position → navigate to exact run → insert TA field after

### Handling Split Citations

If a citation spans multiple runs (e.g., partial italics):
```xml
<w:r><w:rPr><w:i/></w:rPr><w:t>Smith v. Jones</w:t></w:r>
<w:r><w:t>, 123 F.3d 456 (9th Cir. 2020)</w:t></w:r>
```

Insert TA field after the **last** run of the citation.

---

## Implementation Phases

### Phase 1: Citation Detection (Read-Only)

**Goal:** Validate AI can accurately detect citations.

**Deliverables:**
- `toa_text_extractor.py` - Extract text with position markers
- Claude tool definition for citation analysis
- `POST /api/toa/analyze` endpoint
- Basic UI to display detected citations

**Success Criteria:**
- Correctly identifies 95%+ of citations in test documents
- Properly categorizes (cases vs statutes vs rules)
- Groups long/short/Id. forms correctly

### Phase 2: Error Detection & UI

**Goal:** Detect errors and build review interface.

**Deliverables:**
- Error detection logic (short before long, duplicate long, missing Id., orphaned Id.)
- Review UI component showing errors with accept/reject/modify
- Error statistics display

**Success Criteria:**
- Correctly identifies common citation errors
- UI allows easy review and modification

### Phase 3: Text Corrections

**Goal:** Apply user-confirmed corrections to document.

**Deliverables:**
- `toa_service.py` - Orchestrator for corrections
- Text replacement while preserving formatting
- Handle corrections in both body and footnotes

**Success Criteria:**
- Corrections applied without breaking document formatting
- Italics preserved on case names

### Phase 4: TA Code Insertion

**Goal:** Insert TA field codes for all citations.

**Deliverables:**
- `toa_xml_utils.py` - TA field XML construction
- Field insertion at correct positions
- `POST /api/toa/apply` endpoint
- Download of processed document

**Success Criteria:**
- Generated TOA in Word is accurate
- All page numbers captured correctly
- No document corruption

---

## Testing Strategy

### Test Documents Needed

1. **Simple brief** - 5-10 citations, no errors
2. **Error-laden brief** - Intentional mistakes (short before long, duplicate longs, missing Id.)
3. **Complex brief** - Heavy footnotes, many authorities, mixed categories
4. **Edge cases** - String cites, parentheticals, very long citations

### Validation Steps

1. Process document through system
2. Open in Word, generate TOA (References → Insert Table of Authorities)
3. Verify:
   - All authorities appear
   - Page numbers are correct
   - Categories are correct
   - Formatting matches expectations

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Document corruption | Always work on copy; validate XML before save |
| AI misses citations | Allow manual addition in review UI |
| AI misgroups citations | Allow splitting/merging in review UI |
| Position mapping fails | Fall back to text search if position lookup fails |
| Large documents timeout | Chunk processing; async with progress |

---

## Future Enhancements

- **Batch processing** - Multiple documents at once
- **Citation style options** - Bluebook vs California Style Manual
- **Auto-generate TOA** - Insert the actual TOA, not just codes
- **Track changes integration** - Show corrections as tracked changes
- **Supra/infra support** - Handle cross-references to footnotes
