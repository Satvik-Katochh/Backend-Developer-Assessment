"""
Prompt templates for LLM extraction.
Shows evolution: v1 (basic) → v2 (business rules) → v3 (edge cases)
"""


def create_extraction_prompt_v1(subject: str, body: str, port_reference: list) -> str:
    """
    Version 1: Basic extraction prompt.
    Simple instructions to extract fields from email.
    Minimal rules - just basic extraction.
    """
    # Show first 20 ports as examples
    port_examples = "\n".join([
        f"- {port['name']} ({port['code']})"
        for port in port_reference[:20]
    ])

    prompt = f"""You are an expert at extracting shipment details from freight forwarding emails.

Extract the following information from this email:

Email Subject: {subject}
Email Body: {body}

Available Port Codes (UN/LOCODE format - 5 letters: 2-letter country + 3-letter location):
{port_examples}
... and more ports in the reference file.

Return a JSON object with these exact fields:
- origin_port_code: 5-letter UN/LOCODE (e.g., "HKHKG") or null if not found
- origin_port_name: Port name from reference or null
- destination_port_code: 5-letter UN/LOCODE or null
- destination_port_name: Port name from reference or null
- incoterm: FOB, CIF, CFR, EXW, DDP, DAP, FCA, CPT, CIP, or DPU (default: FOB if not mentioned)
- cargo_weight_kg: Weight in kg (number or null)
- cargo_cbm: Volume in CBM (number or null)
- is_dangerous: true if mentions DG/dangerous/hazardous/Class/IMO, false otherwise

Return ONLY valid JSON, no other text. Example format:
{{"origin_port_code": "HKHKG", "origin_port_name": "Hong Kong", "destination_port_code": "INMAA", "destination_port_name": "Chennai", "incoterm": "FOB", "cargo_weight_kg": 500.0, "cargo_cbm": 5.0, "is_dangerous": false}}"""

    return prompt


def create_extraction_prompt_v2(subject: str, body: str, port_reference: list) -> str:
    """
    Version 2: Add business rules and port abbreviations.
    - India detection logic
    - Product line determination
    - Port abbreviations mapping
    - Multiple shipments handling
    - RT units explanation
    """
    port_examples = "\n".join([
        f"- {port['name']} ({port['code']})"
        for port in port_reference[:20]
    ])

    # Common port abbreviations
    abbreviations = """
Common Port Abbreviations:
- SHA, CNSHA = Shanghai
- SIN, SGSIN = Singapore
- SUB, IDSUB = Surabaya
- HCM, VNSGN = Ho Chi Minh
- CPT, ZACPT = Cape Town
- HOU, USHOU = Houston
- MNL, PHMNL = Manila
- PUS, KRPUS = Busan
- JBL, AEJEA = Jebel Ali
- KEL, TWKEL = Keelung
- YOK, JPYOK = Yokohama
- HAM, DEHAM = Hamburg
- MAA, INMAA = Chennai
- BLR, INBLR = Bangalore
- HYD = Hyderabad
- HKG, HKHKG = Hong Kong
- JED, DAM, RUH, SAJED = Jeddah/Dammam/Riyadh (all use SAJED code)
- OSA, JPOSA = Osaka
- GOA, ITGOA = Genoa
- IZM, TRIZM = Izmir
- AMR, TRAMR = Ambarli
- LCH, THLCH = Laem Chabang
- BKK, THBKK = Bangkok
- NSVA, NSH, INNSA = Nhava Sheva
- MUN, INMUN = Mundra
- PKG, MYPKG = Port Klang
- DAC, BDDAC = Dhaka
- GZG, CNGZG = Guangzhou
- NSA, CNNSA = Nansha
- QIN, CNQIN = Qingdao
- SZX, CNSZX = Shenzhen
- TXG, CNTXG = Tianjin/Xingang
"""

    prompt = f"""You are an expert at extracting shipment details from freight forwarding emails.

Extract the following information from this email:

Email Subject: {subject}
Email Body: {body}

IMPORTANT RULES:
1. Body takes precedence over Subject if there are conflicts
2. If email contains multiple shipments, extract ONLY the FIRST shipment mentioned in the email body
3. Indian ports have UN/LOCODE starting with "IN" (e.g., INMAA=Chennai, INBLR=Bangalore, INNSA=Nhava Sheva, INWFD=ICD Whitefield)
4. Product line: If destination port code starts with "IN" → "pl_sea_import_lcl", if origin port code starts with "IN" → "pl_sea_export_lcl"
5. Incoterm: Default to "FOB" if not mentioned or ambiguous
6. Dangerous goods: Set is_dangerous=true if email contains: "DG", "dangerous", "hazardous", "Class" + number (e.g., Class 3), "UN" + number, "IMO", "IMDG"
7. Dangerous goods: Set is_dangerous=false if email contains negations: "non-DG", "non-hazardous", "not dangerous", "non hazardous"
8. RT (Revenue Ton): For LCL shipments, RT typically equals CBM. If only RT is mentioned (e.g., "2.4 RT"), use it as CBM value
9. Missing values should be null (not 0 or empty string)
10. Round weight and CBM to 2 decimal places

{abbreviations}

Available Port Codes (UN/LOCODE format):
{port_examples}
... and more ports in the reference file.

Return a JSON object with these exact fields:
- product_line: "pl_sea_import_lcl" or "pl_sea_export_lcl" (determined from port codes)
- origin_port_code: 5-letter UN/LOCODE or null
- origin_port_name: Port name from reference or null
- destination_port_code: 5-letter UN/LOCODE or null
- destination_port_name: Port name from reference or null
- incoterm: FOB, CIF, CFR, EXW, DDP, DAP, FCA, CPT, CIP, or DPU (default: FOB)
- cargo_weight_kg: Weight in kg (number rounded to 2 decimals or null)
- cargo_cbm: Volume in CBM (number rounded to 2 decimals or null)
- is_dangerous: boolean

Return ONLY valid JSON, no other text."""

    return prompt


def create_extraction_prompt_v3(subject: str, body: str, port_reference: list) -> str:
    """
    Version 3: Comprehensive edge case handling.
    - Multiple shipments (extract first only)
    - Transshipment ports (ignore "via X")
    - Comprehensive port abbreviations
    - RT units handling
    - ICD-specific names
    - Better port matching
    - Unit conversions (lbs to kg)
    - Body vs Subject conflict resolution
    """
    port_examples = "\n".join([
        f"- {port['name']} ({port['code']})"
        for port in port_reference[:25]
    ])

    # Comprehensive port abbreviations
    abbreviations = """
Common Port Abbreviations (use these to match port codes):
- SHA, CNSHA = Shanghai
- SIN, SGSIN = Singapore
- SUB, IDSUB = Surabaya
- HCM, SGN, VNSGN = Ho Chi Minh
- CPT, ZACPT = Cape Town
- HOU, USHOU = Houston
- LAX, USLAX = Los Angeles
- LGB, USLGB = Long Beach
- MNL, PHMNL = Manila
- PUS, KRPUS = Busan
- JBL, JEA, AEJEA = Jebel Ali
- KEL, TWKEL = Keelung
- YOK, JPYOK = Yokohama
- HAM, DEHAM = Hamburg
- MAA, INMAA = Chennai (also: Chennai ICD, ICD Chennai)
- BLR, INBLR = Bangalore ICD (also: ICD Bangalore)
- HYD, INHYD = Hyderabad ICD
- HKG, HKHKG = Hong Kong
- JED, SAJED = Jeddah
- DAM = Dammam (Saudi Arabia)
- RUH = Riyadh (Saudi Arabia)
- OSA, JPOSA = Osaka
- GOA, ITGOA = Genoa
- IZM, TRIZM = Izmir
- AMR, TRAMR = Ambarli (Istanbul)
- LCH, THLCH = Laem Chabang
- BKK, THBKK = Bangkok
- NSA, INNSA = Nhava Sheva (also: JNPT, Mumbai Port)
- MUN, INMUN = Mundra
- PKG, MYPKG = Port Klang
- CMB, LKCMB = Colombo
- DAC, BDDAC = Dhaka
- CAN, GZG, CNGZG = Guangzhou
- NSA, CNNSA = Nansha
- TAO, QIN, CNQIN = Qingdao
- SZX, CNSZX = Shenzhen
- TXG, TSN, CNTXG = Tianjin/Xingang
- WFD, INWFD = ICD Whitefield
- UKB, JPUKB = Kobe (Japan)

Special ICD Names (Indian Inland Container Depots):
- "ICD Whitefield" or "Whitefield ICD" = INWFD
- "ICD Bangalore" or "Bangalore ICD" or "BLR ICD" = INBLR
- "ICD Chennai" or "Chennai ICD" or "MAA ICD" = INMAA
- "ICD Hyderabad" or "Hyderabad ICD" or "HYD ICD" = INMAA (shared code with Chennai)
- "Mundra ICD" = INMUN
- "Nhava Sheva" or "JNPT" = INNSA
- "Bangkok ICD" or "ICD Bangkok" = THBKK
"""

    prompt = f"""You are an expert at extracting shipment details from freight forwarding emails.

Extract the following information from this email:

Email Subject: {subject}
Email Body: {body}

CRITICAL RULES (follow in order of priority):

1. **BODY OVER SUBJECT**: If Subject and Body have conflicting information (different ports, incoterms, etc.), ALWAYS use information from Body - it has more detailed context.

2. **FIRST SHIPMENT ONLY**: If email contains multiple shipments (separated by semicolons, commas, or numbered lists like "1)", "2)"), extract ONLY the FIRST shipment mentioned in the email body. Ignore all subsequent shipments.

3. **IGNORE TRANSSHIPMENT PORTS**: Ports mentioned with "via", "routed via", "transshipment", "through", "transit" are intermediate ports - NOT origin or destination. Use only the actual origin→destination pair.
   Example: "HAM to Chennai via Singapore" → origin=DEHAM, destination=INMAA (ignore Singapore)

4. **INDIA DETECTION**: Indian ports have UN/LOCODE starting with "IN" (e.g., INMAA, INBLR, INNSA, INWFD, INMUN)

5. **PRODUCT LINE**: 
   - If destination port code starts with "IN" → "pl_sea_import_lcl" (importing TO India)
   - If origin port code starts with "IN" → "pl_sea_export_lcl" (exporting FROM India)

6. **INCOTERM RULES**:
   - Extract incoterm exactly as mentioned: FOB, CIF, CFR, EXW, DDP, DAP, FCA, CPT, CIP, DPU
   - Default to "FOB" only if NO incoterm is mentioned at all
   - If ambiguous (e.g., "FOB or CIF"), default to "FOB"
   - Note: FCA is a valid incoterm - extract it if mentioned

7. **DANGEROUS GOODS** (check negations FIRST):
   - If "non-DG", "non-hazardous", "not dangerous", "non hazardous" → is_dangerous=false
   - If "DG", "dangerous", "hazardous", "Class X" (number), "UN XXXX" (number), "IMO", "IMDG" → is_dangerous=true
   - No mention → is_dangerous=false

8. **RT (REVENUE TON) UNITS**: For LCL shipments, RT = CBM (volume). 
   - If "X RT" is mentioned, use RT value as cargo_cbm
   - Example: "2.4 RT" → cargo_cbm=2.4, cargo_weight_kg=null (unless weight separately mentioned)

9. **UNIT CONVERSIONS**:
   - Weight in lbs → convert to kg: lbs × 0.453592, round to 2 decimals
   - Weight in tonnes/MT → convert to kg: tonnes × 1000
   - Dimensions (L×W×H) → do NOT calculate CBM, set cargo_cbm=null

10. **NULL VALUES**: Missing values should be null (not 0 or empty string). "TBD", "N/A", "to be confirmed" → null

11. **ROUNDING**: Round cargo_weight_kg and cargo_cbm to 2 decimal places

12. **PORT NAMES**: Use canonical port name from reference file for the matched code

{abbreviations}

Available Port Codes (UN/LOCODE format):
{port_examples}
... and more ports in the reference file.

Return a JSON object with these exact fields:
- product_line: "pl_sea_import_lcl" or "pl_sea_export_lcl"
- origin_port_code: 5-letter UN/LOCODE or null
- origin_port_name: Port name from reference or null
- destination_port_code: 5-letter UN/LOCODE or null
- destination_port_name: Port name from reference or null
- incoterm: FOB, CIF, CFR, EXW, DDP, DAP, FCA, CPT, CIP, or DPU
- cargo_weight_kg: Weight in kg (number or null)
- cargo_cbm: Volume in CBM (number or null)
- is_dangerous: boolean

Return ONLY valid JSON, no other text."""

    return prompt
