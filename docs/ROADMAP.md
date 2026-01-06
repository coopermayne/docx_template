# Project Roadmap

## Current Features (Completed)

- [x] Session-based RFP processing workflow
- [x] PDF upload and parsing with text extraction
- [x] AI-powered case info extraction from RFP first page
- [x] AI-powered request analysis with response suggestions
- [x] Responsive document management with Bates number detection
- [x] Customizable objections library (Supabase)
- [x] Multi-user support with profiles
- [x] Custom document templates per user (Supabase Storage)
- [x] Word document generation from templates
- [x] Motion opposition document generation

---

## Planned Features

### Table of Authorities Citation Processing

**Status:** Planning
**Priority:** High
**Documentation:** [toa-citation-feature.md](toa-citation-feature.md)

Automatically process legal briefs to insert Word Table of Authorities (TOA) field codes:

- Upload DOCX legal brief
- AI detects all citations (cases, statutes, rules, treatises)
- AI identifies citation errors:
  - Short cite before long cite
  - Duplicate long citations
  - Missing Id. citations
  - Orphaned Id. references
- User reviews and confirms proposed corrections
- System applies corrections and inserts TA field codes
- Download processed document ready for TOA generation in Word

**Implementation Phases:**
1. Citation detection (read-only analysis)
2. Error detection and review UI
3. Text corrections with formatting preservation
4. TA field code insertion

---

### Retainer Agreements

**Status:** Planned
**Priority:** Medium

Generate client engagement letters and retainer agreements:

- Template-based generation with firm/attorney info
- Client information input
- Fee structure configuration (hourly, contingency, flat fee, hybrid)
- Scope of representation
- Standard terms and conditions

---

### Complaint Drafting

**Status:** Planned
**Priority:** Medium

AI-assisted initial pleading generation:

- Case type selection (PI, employment, contract, etc.)
- Party information
- Cause of action templates
- Factual allegation assistance
- Prayer for relief generation

---

### Declarations

**Status:** Planned
**Priority:** Medium

Generate witness statement documents:

- Declarant information
- Fact organization and structuring
- Proper declaration formatting
- Exhibit references
- Signature blocks with penalty of perjury language

---

### Discovery Requests (Propounding)

**Status:** Planned
**Priority:** Medium

Generate outgoing discovery requests:

- Interrogatories (Form and Special)
- Requests for Admission (RFAs)
- Requests for Production (RFPs) - propounding side
- Case-type specific question templates
- Definitions and instructions

---

## Future Considerations

- **Batch RFP Processing** - Handle multiple RFPs in single session
- **Response Templates** - Save and reuse common response patterns
- **Export Formats** - PDF export in addition to DOCX
- **Collaboration** - Multiple users working on same session
- **Audit Trail** - Track changes and revision history
- **Integration** - Connect with legal practice management systems
