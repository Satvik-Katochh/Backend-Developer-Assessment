# Prompt Evolution Guide: Complete Documentation

This document provides an in-depth explanation of how the extraction prompts evolved from v1 to v3, with specific examples from the email dataset, failure analysis, and the reasoning behind each improvement.

---

## Table of Contents

1. [Overview](#overview)
2. [Version 1: Basic Extraction](#version-1-basic-extraction)
3. [Version 2: Business Rules](#version-2-business-rules)
4. [Version 3: Comprehensive Edge Cases](#version-3-comprehensive-edge-cases)
5. [Edge Cases Deep Dive](#edge-cases-deep-dive)
6. [Test Results Summary](#test-results-summary)
7. [Key Learnings](#key-learnings)

---

## Overview

The extraction system processes freight forwarding pricing inquiry emails to extract structured shipment details. The prompt evolution followed a systematic approach:

1. **v1**: Get basic extraction working
2. **v2**: Add business rules based on failure analysis
3. **v3**: Handle edge cases and improve robustness

### Evaluation Fields (9 per email)
| Field | Type | Notes |
|-------|------|-------|
| product_line | string | "pl_sea_import_lcl" or "pl_sea_export_lcl" |
| origin_port_code | string | 5-letter UN/LOCODE (e.g., "CNSHA") |
| origin_port_name | string | Canonical name from reference |
| destination_port_code | string | 5-letter UN/LOCODE |
| destination_port_name | string | Canonical name from reference |
| incoterm | string | FOB, CIF, FCA, etc. |
| cargo_weight_kg | float | Weight in kg or null |
| cargo_cbm | float | Volume in CBM or null |
| is_dangerous | boolean | true/false |

---

## Version 1: Basic Extraction

### Approach
Simple extraction instructions with minimal context. Just told the LLM to extract fields from the email.

### Accuracy: ~65%

### What v1 Did
- Basic field extraction
- Simple port matching
- FOB as default incoterm
- Basic DG detection

### What v1 Did NOT Have
1. No port abbreviation mapping
2. No product_line determination logic
3. No multiple shipments handling
4. No transshipment port handling
5. No RT (Revenue Ton) explanation
6. No conflict resolution (Subject vs Body)

### Specific Failures

#### Failure 1: Port Abbreviations Not Recognized
**Email ID**: EMAIL_005
```
Subject: Singapore to Chennai
Body: Non-stackable 1.1 cbm SIN → Chennai.
```

| Field | v1 Result | Expected | Issue |
|-------|-----------|----------|-------|
| origin_port_code | null or "SIN" | SGSIN | "SIN" not mapped to SGSIN |
| origin_port_name | null | Singapore | No name without code |

**Root Cause**: v1 had no abbreviation mapping. The LLM didn't know SIN = SGSIN = Singapore.

---

#### Failure 2: Product Line Not Determined
**Email ID**: EMAIL_017
```
Subject: DG RFQ // SHA → BLR ICD
Body: Hi Team, Need LCL DG SHA→BLR ICD. UN 2430 Amines Liquid PG II, 400 KG/1.1 CBM, supplier shipping CIF SHA.
```

| Field | v1 Result | Expected | Issue |
|-------|-----------|----------|-------|
| product_line | null | pl_sea_import_lcl | No logic to determine |

**Root Cause**: v1 didn't have the rule "destination IN = import, origin IN = export".

---

#### Failure 3: Incoterm FCA Not Extracted
**Email ID**: EMAIL_003
```
Subject: SEA IMPORT RFQ // Shanghai to Chennai // Auto Components
Body: ...Terms FCA Shanghai. Commodity urgent auto components non-DG 260 KGS 1.0 CBM...
```

| Field | v1 Result | Expected | Issue |
|-------|-----------|----------|-------|
| incoterm | FOB | FCA | LLM defaulted to FOB, ignored FCA |

**Root Cause**: v1 defaulted to FOB too aggressively without checking for explicit incoterms.

---

#### Failure 4: Multiple Shipments Confusion
**Email ID**: EMAIL_007
```
Subject: LCL RFQ ex Saudi to India ICD
Body: JED→MAA ICD 1.9 cbm; DAM→BLR ICD 3 RT; RUH→HYD ICD 850kg.
```

| Field | v1 Result | Expected | Issue |
|-------|-----------|----------|-------|
| origin_port_code | Mixed/confused | SAJED | 3 shipments, extracted wrong one |
| cargo_cbm | Various | 1.9 | Mixed data from multiple shipments |

**Root Cause**: v1 had no instruction to extract only the first shipment.

---

## Version 2: Business Rules

### Approach
Added explicit business rules, port abbreviations, and product line logic based on v1 failures.

### Accuracy: ~78% (improvement: +13%)

### Key Changes from v1

1. **Comprehensive Port Abbreviation Mapping**
```
- SHA, CNSHA = Shanghai
- SIN, SGSIN = Singapore
- MAA, INMAA = Chennai
- JED, DAM, RUH, SAJED = Jeddah/Dammam/Riyadh
...
```

2. **Product Line Determination Rule**
```
If destination port code starts with "IN" → "pl_sea_import_lcl"
If origin port code starts with "IN" → "pl_sea_export_lcl"
```

3. **Multiple Shipments Rule**
```
If email contains multiple shipments (separated by semicolons or numbered), 
extract ONLY the FIRST shipment mentioned in the email body
```

4. **RT Units Explanation**
```
RT (Revenue Ton): For LCL shipments, RT = CBM. 
If "X RT" is mentioned, use RT value as cargo_cbm
```

5. **Dangerous Goods with Negation Handling**
```
Check for negations FIRST: "non-DG", "non-hazardous", "not dangerous"
If negation found → is_dangerous=false
Only then check for positive keywords
```

### Improvements Achieved

| Email ID | v1 Result | v2 Result | Fixed? |
|----------|-----------|-----------|--------|
| EMAIL_005 | origin_port_code: null | origin_port_code: SGSIN | ✅ |
| EMAIL_007 | Mixed shipment data | First shipment extracted | ✅ |
| EMAIL_003 | incoterm: FOB | incoterm: FCA | ✅ |
| EMAIL_017 | product_line: null | product_line: pl_sea_import_lcl | ✅ |

### Remaining Issues in v2

1. **ICD Whitefield Not Matched**
   - EMAIL_019: "ICD WHITEFIELD" → INWFD not recognized
   
2. **Transshipment Ports Included**
   - EMAIL_019: "via Chennai" incorrectly set Chennai as destination
   - EMAIL_037: "via HKG" confused the extraction
   
3. **Missing US Port Abbreviations**
   - EMAIL_043: LAX, LGB not mapped

---

## Version 3: Comprehensive Edge Cases

### Approach
Added ICD-specific names, transshipment handling, more port abbreviations, and clearer body vs subject precedence.

### Accuracy: ~85-90% (improvement: +7-12%)

### Key Changes from v2

1. **Transshipment Port Rule**
```
CRITICAL RULE: Ignore transshipment/intermediate ports mentioned with 
"via", "routed via", "transshipment", "through" - use only the final 
origin→destination pair.

Example: "HAM to Chennai via Singapore" → origin=DEHAM, destination=INMAA 
(ignore Singapore)
```

2. **ICD-Specific Mappings**
```
Special ICD Names (Indian Inland Container Depots):
- "ICD Whitefield" or "Whitefield ICD" = INWFD
- "ICD Bangalore" or "Bangalore ICD" or "BLR ICD" = INBLR
- "ICD Chennai" or "Chennai ICD" or "MAA ICD" = INMAA
- "Bangkok ICD" or "ICD Bangkok" = THBKK
```

3. **More Port Abbreviations**
```
- LAX, USLAX = Los Angeles
- LGB, USLGB = Long Beach
- CMB, LKCMB = Colombo
- UKB, JPUKB = Kobe (Japan)
```

4. **Explicit Body Over Subject Rule**
```
CRITICAL RULE: If Subject and Body have conflicting information 
(different ports, incoterms, etc.), ALWAYS use information from Body - 
it has more detailed context.
```

5. **Unit Conversions**
```
- Weight in lbs → convert to kg: lbs × 0.453592
- Weight in tonnes/MT → convert to kg: tonnes × 1000
- Dimensions (L×W×H) → do NOT calculate CBM, set cargo_cbm=null
```

### Final Improvements

| Email ID | v2 Issue | v3 Solution | Result |
|----------|----------|-------------|--------|
| EMAIL_019 | ICD Whitefield not matched | Added WFD→INWFD mapping | ✅ 100% |
| EMAIL_037 | "via HKG" confused extraction | Transshipment rule | ✅ 100% |
| EMAIL_001 | Export not detected | Product line rule | ✅ 100% |
| EMAIL_003 | FCA sometimes missed | Explicit FCA handling | ✅ 100% |

---

## Edge Cases Deep Dive

### 1. Multiple Shipments in One Email

**Affected Emails**: EMAIL_007, EMAIL_013, EMAIL_015, EMAIL_043

**Example - EMAIL_007**:
```
Subject: LCL RFQ ex Saudi to India ICD
Body: JED→MAA ICD 1.9 cbm; DAM→BLR ICD 3 RT; RUH→HYD ICD 850kg.
```

**Analysis**:
- Contains 3 separate shipments separated by semicolons
- README says: "Extract the shipment that appears first in the email body"
- First shipment: JED→MAA ICD 1.9 cbm

**Expected Extraction**:
```json
{
  "origin_port_code": "SAJED",
  "origin_port_name": "Jeddah",
  "destination_port_code": "INMAA", 
  "destination_port_name": "Chennai",
  "cargo_cbm": 1.9,
  "cargo_weight_kg": null
}
```

**Note**: Ground truth aggregates all shipments, but we follow README which says "first shipment only". This is a deliberate design decision documented in Known Limitations.

---

### 2. Transshipment/Intermediate Ports

**Affected Emails**: EMAIL_019, EMAIL_023, EMAIL_037

**Example - EMAIL_019**:
```
Subject: ICD Whitefield via Chennai
Body: HAM to ICD WHITEFIELD, routed via Chennai. 3.5 cbm, 820 kg. FOB Hamburg.
```

**Analysis**:
- Origin: Hamburg (HAM → DEHAM)
- Destination: ICD Whitefield (INWFD)
- "via Chennai" is transshipment port - should be IGNORED

**Incorrect Extraction (v1/v2)**:
```json
{
  "destination_port_code": "INMAA",  // Wrong! Chennai is transshipment
  "destination_port_name": "Chennai"
}
```

**Correct Extraction (v3)**:
```json
{
  "destination_port_code": "INWFD",  // Correct! Final destination
  "destination_port_name": "ICD Whitefield"
}
```

**v3 Rule Added**:
> Ignore transshipment/intermediate ports mentioned with "via", "routed via", "transshipment", "through" - use only the final origin→destination pair.

---

### 3. Port Abbreviations

**Affected Emails**: EMAIL_005, EMAIL_006, EMAIL_009, EMAIL_017, EMAIL_029, EMAIL_043

**Example - EMAIL_005**:
```
Body: Non-stackable 1.1 cbm SIN → Chennai.
```

**Analysis**:
- "SIN" is abbreviation for Singapore
- Need to map: SIN → SGSIN → Singapore

**v1 Problem**: No abbreviation mapping
**v2/v3 Solution**: Comprehensive abbreviation list in prompt

**Key Abbreviations Added**:
| Abbreviation | UN/LOCODE | Port Name |
|--------------|-----------|-----------|
| SHA | CNSHA | Shanghai |
| SIN | SGSIN | Singapore |
| MAA | INMAA | Chennai |
| HKG | HKHKG | Hong Kong |
| JED | SAJED | Jeddah |
| LAX | USLAX | Los Angeles |
| LGB | USLGB | Long Beach |

---

### 4. Dangerous Goods with Negations

**Affected Emails**: EMAIL_001, EMAIL_003, EMAIL_008, EMAIL_040

**Example - EMAIL_001**:
```
Body: ...tyre moulds and accessories, 1,980 KGS, 3.8 CBM, wooden crates, non-DG, stackable.
```

**Analysis**:
- Contains "DG" but preceded by "non-"
- This is NEGATION - cargo is NOT dangerous

**v1 Problem**: Detected "DG" → set is_dangerous=true (WRONG!)
**v2/v3 Solution**: Check for negations FIRST

**Rule Added**:
> Check for negations FIRST: "non-DG", "non-hazardous", "not dangerous", "non hazardous"
> If negation found → is_dangerous=false
> Only then check for positive keywords

---

### 5. RT (Revenue Ton) Units

**Affected Emails**: EMAIL_007, EMAIL_015, EMAIL_024, EMAIL_034, EMAIL_035, EMAIL_043

**Example - EMAIL_024**:
```
Subject: Jebel Ali to Chennai ICD
Body: Need LCL rate 2.4 RT Jebel Ali → Chennai ICD.
```

**Analysis**:
- "2.4 RT" = 2.4 Revenue Tons
- For LCL shipments: RT = CBM (volume, not weight)
- cargo_cbm = 2.4
- cargo_weight_kg = null (weight not mentioned)

**Rule Added**:
> RT (Revenue Ton): For LCL shipments, RT = CBM (volume).
> If "X RT" is mentioned, use RT value as cargo_cbm
> Example: "2.4 RT" → cargo_cbm=2.4, cargo_weight_kg=null

**Important Note**: Ground truth sometimes calculates weight from RT (RT × 1000), but README doesn't specify this conversion. We follow README and set weight to null if not explicitly mentioned.

---

### 6. Subject vs Body Conflicts

**Example Scenario**:
```
Subject: RATE REQ // FOB // HK TO MUMBAI
Body: Please quote CIF terms for shipment from Hong Kong to Chennai
```

**Analysis**:
- Subject says: FOB, destination Mumbai
- Body says: CIF, destination Chennai
- Body has more detailed context → Body wins

**Expected Extraction**:
```json
{
  "incoterm": "CIF",  // From body, not subject
  "destination_port_code": "INMAA",  // Chennai from body, not Mumbai
  "destination_port_name": "Chennai"
}
```

**Rule Added**:
> BODY OVER SUBJECT: If Subject and Body have conflicting information (different ports, incoterms, etc.), ALWAYS use information from Body - it has more detailed context.

---

## Test Results Summary

### v3 Test Results (Key Emails)

| Email ID | Accuracy | Notes |
|----------|----------|-------|
| EMAIL_001 | 100% | Export shipment - correctly detected |
| EMAIL_003 | 100% | FCA incoterm correctly extracted |
| EMAIL_019 | 100% | Transshipment handled, ICD Whitefield matched |
| EMAIL_037 | 100% | "via HKG" correctly ignored |
| EMAIL_007 | 77.8% | First shipment extracted per README |
| EMAIL_023 | 88.9% | "Bangkok" vs "Bangkok ICD" (minor name difference) |
| EMAIL_006 | 77.8% | FCA vs FOB conflict (see Known Limitations) |

### Accuracy Progression

| Version | Accuracy | Key Improvements |
|---------|----------|------------------|
| v1 | ~65% | Basic extraction |
| v2 | ~78% | +Port abbreviations, +Product line, +RT handling |
| v3 | ~85-90% | +Transshipment, +ICD names, +Body precedence |

---

## Key Learnings

### 1. Iterative Improvement Works
Each version addressed specific failures from the previous version. Starting simple and iterating based on actual test results is more effective than trying to anticipate all edge cases upfront.

### 2. README is Source of Truth
When ground truth conflicts with README (e.g., EMAIL_007 aggregates shipments), follow README. Document these discrepancies clearly.

### 3. Post-Processing Complements LLM
Some rules are deterministic (product_line from port codes) and are better handled in post-processing than relying on LLM:
- Product line determination
- Numeric rounding
- Canonical port name lookup

### 4. Abbreviation Mapping is Critical
Freight forwarding uses many abbreviations (SHA, SIN, MAA, etc.). Comprehensive mapping in the prompt significantly improves accuracy.

### 5. Negation Detection Must Come First
For dangerous goods, checking negations before positive keywords prevents false positives like "non-DG" being detected as dangerous.

### 6. Context Matters for Transshipment
Words like "via", "routed via", "through" indicate intermediate ports. The LLM needs explicit guidance to ignore these.

---

## Files Reference

| File | Purpose |
|------|---------|
| `prompts.py` | Contains v1, v2, v3 prompt templates |
| `extract.py` | Main extraction script with post-processing |
| `test_single_email.py` | Test individual emails with any prompt version |
| `evaluate.py` | Calculate overall accuracy |
| `SUBMISSION_README.md` | Main submission documentation |

---

## Quick Test Commands

```bash
# Test any email with any prompt version
python test_single_email.py EMAIL_007 v1
python test_single_email.py EMAIL_007 v2
python test_single_email.py EMAIL_007 v3

# Run full extraction
python extract.py

# Calculate accuracy
python evaluate.py
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
