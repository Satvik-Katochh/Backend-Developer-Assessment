---
name: LLM Email Extraction System
overview: Build a complete LLM-powered email extraction system with iterative prompt development, comprehensive edge case handling, and post-processing validation. Start with sample testing, then scale to all 50 emails.
todos:
  - id: setup
    content: "Create project structure: schemas.py, prompts.py, extract.py, evaluate.py, requirements.txt, .env.example"
    status: completed
  - id: schemas
    content: Define Pydantic ShipmentExtraction model with all 9 fields, Optional types, Field validations
    status: completed
    dependencies:
      - setup
  - id: port_matching
    content: Build port reference loader with code_to_name and name_to_code lookups, handle abbreviations
    status: completed
    dependencies:
      - setup
  - id: prompt_v1
    content: Create basic extraction prompt v1, test on 5 sample emails (EMAIL_001, 002, 006, 007, 024)
    status: completed
    dependencies:
      - schemas
      - port_matching
  - id: extract_basic
    content: Build extract.py with Groq API calls, retry logic, basic JSON parsing, test on 5 samples
    status: completed
    dependencies:
      - prompt_v1
  - id: evaluate_script
    content: Create evaluate.py with field-by-field comparison logic and accuracy metrics
    status: completed
    dependencies:
      - extract_basic
  - id: prompt_v2
    content: Enhance prompt v2 with business rules (India detection, product line, incoterm defaults, DG detection), test on 10 samples
    status: completed
    dependencies:
      - evaluate_script
  - id: post_processing
    content: "Add post-processing: port matching fallback, product line determination, RT unit handling, numeric rounding"
    status: completed
    dependencies:
      - prompt_v2
  - id: prompt_v3
    content: Enhance prompt v3 with edge cases (multiple shipments, transshipment, abbreviations, RT units), test on all 50 emails
    status: completed
    dependencies:
      - post_processing
  - id: full_run
    content: Run extraction on all 50 emails, generate output.json, run evaluation, document accuracy metrics
    status: pending
    dependencies:
      - prompt_v3
  - id: documentation
    content: Write README with setup, prompt evolution log (specific email IDs), accuracy metrics, edge cases, system design answers
    status: completed
    dependencies:
      - full_run
---

# LLM Email Extraction System - Complete Implementation Plan

## Architecture Overview

```
emails_input.json → extract.py → Groq LLM API → Post-processing → output.json
                                                      ↓
                                              evaluate.py → Accuracy Metrics
```

## Phase 1: Foundation Setup (30 min)

### 1.1 Project Structure

Create all required files:

- `schemas.py` - Pydantic models for validation
- `prompts.py` - Prompt templates (v1, v2, v3)
- `extract.py` - Main extraction script
- `evaluate.py` - Accuracy calculator
- `requirements.txt` - Dependencies
- `.env.example` - API key template
- `.env` - Actual API key (gitignored)

### 1.2 Dependencies

- `groq` - LLM API client
- `pydantic` - Data validation
- `python-dotenv` - Environment variables

## Phase 2: Data Models (schemas.py)

### 2.1 Pydantic Schema

Define `ShipmentExtraction` model with:

- All 9 required fields (id, product_line, ports, incoterm, weight, CBM, is_dangerous)
- `Optional[float]` for numeric fields (can be null)
- `Field(ge=0)` validation for weight/CBM (must be >= 0 if provided)
- Default values: `incoterm="FOB"`, `is_dangerous=False`

**Why**: Automatic validation catches errors early, ensures type safety.

## Phase 3: Port Matching System

### 3.1 Port Reference Loader

Create lookup dictionaries:

- `code_to_name`: Maps port code → canonical name (for output)
- `name_to_code`: Maps all name variations → port code (for matching)
- Handle abbreviations: SHA→Shanghai, SIN→Singapore, HKG→Hong Kong, etc.
- Handle multiple names per code (e.g., "Chennai" and "Chennai ICD" both → INMAA)

### 3.2 Port Matching Function

- Normalize input (lowercase, strip)
- Direct match first
- Partial match (contains/substring)
- Return (code, name) tuple or (None, None)

**Edge cases handled**:

- Abbreviations (SHA, SIN, SUB, HCM, CPT, HOU, MNL, PUS, JBL, KEL, YOK, HAM)
- Name variations ("Chennai ICD" vs "Chennai")
- Multiple ports per code in reference file

## Phase 4: Prompt Development (Iterative)

### 4.1 Prompt v1: Basic Extraction

- Simple instructions to extract fields
- Include port reference list (first 20 ports as examples)
- Request JSON output only
- **Test on 3-5 sample emails first**

### 4.2 Prompt v2: Add Business Rules

Based on v1 errors, add:

- India detection logic (ports starting with "IN")
- Product line determination (destination IN → import, origin IN → export)
- Incoterm defaulting (FOB if missing)
- Dangerous goods detection keywords
- **Test on 10 emails, check accuracy**

### 4.3 Prompt v3: Edge Cases

Add explicit handling for:

- Multiple shipments (extract first only)
- Subject vs Body conflicts (body wins)
- Transshipment ports (ignore "via X", use origin→destination)
- RT units (Revenue Ton - typically equals CBM for LCL)
- Port abbreviations mapping
- **Test on all 50 emails**

## Phase 5: Main Extraction Script (extract.py)

### 5.1 Core Flow

1. Load emails and port reference
2. For each email:

   - Combine subject + body
   - Create prompt (use latest version)
   - Call Groq API with retry logic (3 attempts, exponential backoff)
   - Parse JSON response (handle markdown code blocks)
   - Validate with Pydantic
   - Post-process (port matching, product line logic)
   - Add to results
   - Rate limiting (2 second delay between requests)

### 5.2 Error Handling

- API timeouts → retry with backoff
- Invalid JSON → return nulls for all fields (preserve email ID)
- Validation errors → log and return nulls
- Never skip emails (always include in output.json)

### 5.3 Post-Processing Logic

After LLM extraction, apply deterministic rules:

- **Port matching**: If LLM didn't find code, try matching from email text
- **Product line**: Determine from port codes (not LLM)
- **Numeric rounding**: Round weight/CBM to 2 decimals
- **RT conversion**: Handle "RT" units (check ground truth: EMAIL_024=2400kg, EMAIL_034=1500kg, EMAIL_035=229.4kg)
- **Port name**: Always use canonical name from reference file

## Phase 6: Edge Cases Identified

### 6.1 Multiple Shipments (Extract First Only)

- EMAIL_007: "JED→MAA ICD 1.9 cbm; DAM→BLR ICD 3 RT; RUH→HYD ICD 850kg"
- EMAIL_013: "Ambarli→MAA ICD 2.4 cbm; Ambarli→HYD ICD 600kg; Izmir→BLR ICD 1.2 cbm"
- EMAIL_015: "JBL→MAA ICD 2.2 cbm; JBL→HYD ICD 750kg; JBL→BLR ICD 1.9 cbm"
- EMAIL_043: "LAX→MAA ICD 2.3 cbm; HOU→HYD ICD 850kg; LGB→BLR ICD 1 RT"
- **Solution**: Explicitly instruct LLM to extract first shipment only

### 6.2 Port Abbreviations

- SHA (Shanghai), SIN (Singapore), SUB (Surabaya), HCM (Ho Chi Minh)
- CPT (Cape Town), HOU (Houston), MNL (Manila), PUS (Busan)
- JBL (Jebel Ali), KEL (Keelung), YOK (Yokohama), HAM (Hamburg)
- MAA (Chennai), BLR (Bangalore), HYD (Hyderabad)
- **Solution**: Create abbreviation mapping, include in prompt

### 6.3 RT (Revenue Ton) Units

- EMAIL_024: "2.4 RT" → 2400.0 kg (ground truth shows 2400kg, 2.4 CBM)
- EMAIL_026: "1 RT" → likely 1000kg or 1.0 CBM
- EMAIL_034: "1.5 RT" → 1500.0 kg (ground truth)
- EMAIL_035: "0.2 RT" → 229.4 kg (ground truth)
- **Solution**: RT typically = max(weight, CBM), but check context. For LCL, often equals CBM. Include in prompt.

### 6.4 Transshipment Ports (Ignore Intermediate)

- EMAIL_019: "HAM to ICD WHITEFIELD, routed via Chennai" → origin=Hamburg, dest=Whitefield
- EMAIL_023: "Chennai to Bangkok ICD via Laem Chabang" → origin=Chennai, dest=Bangkok ICD
- EMAIL_027: "Ambarli to ICD Bangalore via Chennai" → origin=Ambarli, dest=Bangalore ICD
- EMAIL_037: "Guangzhou to Chennai, LCL via HKG" → origin=Guangzhou, dest=Chennai
- **Solution**: Explicitly instruct to ignore "via", "routed via", "transshipment" ports

### 6.5 Dangerous Goods Detection

- Keywords: "DG", "dangerous", "hazardous", "Class 3", "Class 9", "UN 1993", "IMO", "IMDG"
- Negations: "non-DG", "non-hazardous", "not dangerous" → false
- **Solution**: Include keyword list and negation handling in prompt

### 6.6 Subject vs Body Conflicts

- Example from README: Subject says "FOB", Body says "CIF" → Body wins
- **Solution**: Explicitly state "Body takes precedence over Subject"

### 6.7 Generic Port Names

- EMAIL_011: "Japan" → JPUKB (generic Japan port)
- EMAIL_018: Ground truth shows KRPUS for destination (looks like error, should be INMAA?)
- **Solution**: Handle generic names, match to closest port in reference

### 6.8 Country-Level Mentions

- EMAIL_038: "China → India. Port is Tianjin/Xingang. Destination Chennai port"
- EMAIL_050: "Busan to India, 4 cbm"
- **Solution**: Extract specific ports mentioned, ignore country names

### 6.9 Multiple Port Names Per Code

- Reference file has multiple entries: "Chennai" and "Chennai ICD" both map to INMAA
- **Solution**: Use first canonical name found in reference file

### 6.10 Missing/Incomplete Data

- EMAIL_002: No weight, only CBM
- EMAIL_005: No weight, only CBM
- EMAIL_009: No weight, only CBM
- **Solution**: Return null for missing fields (not 0 or "")

## Phase 7: Evaluation Script (evaluate.py)

### 7.1 Comparison Logic

- String fields: Case-insensitive, whitespace-trimmed comparison
- Float fields: Round to 2 decimals, then exact match
- Null fields: null only equals null
- Boolean fields: Exact match

### 7.2 Metrics Calculation

Calculate accuracy for each of 9 fields:

- product_line
- origin_port_code
- origin_port_name
- destination_port_code
- destination_port_name
- incoterm
- cargo_weight_kg
- cargo_cbm
- is_dangerous

Overall accuracy = (total correct fields) / (total fields)

### 7.3 Output Format

Print readable table showing:

- Field name
- Accuracy percentage
- Correct/Total counts
- Overall accuracy

## Phase 8: Testing Strategy

### 8.1 Sample Testing (Before Full Run)

1. Test on EMAIL_001 (export case)
2. Test on EMAIL_002 (simple import, no weight)
3. Test on EMAIL_006 (dangerous goods)
4. Test on EMAIL_007 (multiple shipments)
5. Test on EMAIL_018 (check port matching issue)
6. Test on EMAIL_024 (RT units)
7. Test on EMAIL_028 (destination mismatch - Qingdao to BLR ICD, but ground truth shows INMAA as destination_port_code - verify this)

### 8.2 Iteration Process

1. Run on sample emails
2. Compare to ground truth manually
3. Identify error patterns
4. Update prompt (v1 → v2 → v3)
5. Re-test on samples
6. Once samples pass, run on all 50
7. Run evaluation script
8. Document specific email IDs that had issues

## Phase 9: Documentation (README.md)

### 9.1 Setup Instructions

- Virtual environment setup
- Install dependencies
- API key configuration
- Run commands

### 9.2 Prompt Evolution Log

Document each version with:

- Accuracy achieved
- Specific issues found
- Example email IDs that failed
- Changes made
- Why changes were made

### 9.3 Accuracy Metrics

- Field-by-field accuracy
- Overall accuracy
- Specific email IDs that failed

### 9.4 Edge Cases Handled

Document at least 3 specific cases:

- Email ID
- Problem description
- Solution implemented

### 9.5 System Design Answers

Answer 3 questions (2-3 paragraphs each):

1. Scale to 10,000 emails/day, 99% within 5 min, $500/month budget
2. Monitoring accuracy drops from 90% to 70%
3. Multilingual support (30% Mandarin, 20% Hindi)

## Implementation Order

1. **Setup** → Create files, install dependencies
2. **Schemas** → Define Pydantic models, test validation
3. **Port Matching** → Build lookup system, test matching
4. **Prompt v1** → Basic extraction, test on 5 samples
5. **Extract Script** → Basic flow, test on 5 samples
6. **Evaluate Script** → Compare results, identify errors
7. **Prompt v2** → Add business rules, test on 10 samples
8. **Post-processing** → Add deterministic rules
9. **Prompt v3** → Add edge cases, test on all 50
10. **Full Run** → Process all emails, generate output.json
11. **Documentation** → Write README with all required sections

## Key Files to Create

- `schemas.py` - Pydantic models
- `prompts.py` - Three prompt versions with evolution
- `extract.py` - Main extraction with retry, post-processing
- `evaluate.py` - Accuracy calculator
- `requirements.txt` - groq, pydantic, python-dotenv
- `.env.example` - GROQ_API_KEY=your_key_here
- `README.md` - Complete documentation

## Success Criteria

- All 50 emails processed (no skipped emails)
- output.json generated with all results
- Evaluation shows >80% accuracy (target: 90%+)
- Code is clean, typed, with error handling
- README documents prompt evolution with specific examples
- Edge cases explicitly handled and documented
