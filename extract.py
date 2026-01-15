"""
Main extraction script.
Processes emails using Groq LLM API with retry logic and post-processing.
"""
import json
import os
import time
import re
from typing import Dict, List, Tuple, Optional
from groq import Groq
from dotenv import load_dotenv
from schemas import ShipmentExtraction
from prompts import create_extraction_prompt_v1, create_extraction_prompt_v2, create_extraction_prompt_v3

# Prompt version to use (change this for iterative testing)
PROMPT_VERSION = "v3"  # Options: "v1", "v2", "v3"

# Load environment variables
load_dotenv()

# Initialize Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def load_port_reference(file_path: str = "port_codes_reference.json") -> Tuple[Dict[str, str], Dict[str, str], Dict[str, List[str]]]:
    """
    Load port codes and create lookup dictionaries.
    Returns: (code_to_name, name_to_code, code_to_all_names)
    """
    with open(file_path, 'r') as f:
        ports = json.load(f)

    code_to_name = {}  # {"HKHKG": "Hong Kong"} - preferred canonical name
    name_to_code = {}  # {"hong kong": "HKHKG", "hk": "HKHKG"}
    # {"INMAA": ["Chennai", "Chennai ICD", "Chennai ICD / ..."]} - all names for a code
    code_to_all_names = {}

    for port in ports:
        code = port["code"]
        name = port["name"]

        # Store all names for each code
        if code not in code_to_all_names:
            code_to_all_names[code] = []
        code_to_all_names[code].append(name)

        # Store canonical mapping (prefer combined names with "/" over simple names)
        if code not in code_to_name:
            code_to_name[code] = name
        else:
            # Prefer combined names (contain "/") over simple names
            current_name = code_to_name[code]
            if "/" in name and "/" not in current_name:
                code_to_name[code] = name
            elif "/" not in name and "/" in current_name:
                # Keep the combined name
                pass
            elif len(name) > len(current_name):
                # Prefer longer names (usually more descriptive)
                code_to_name[code] = name

        # Store all name variations (lowercase for matching)
        normalized_name = name.lower().strip()
        name_to_code[normalized_name] = code

        # Handle common abbreviations
        abbreviations = {
            "hong kong": ["hk", "hkg"],
            "shanghai": ["sha"],
            "singapore": ["sin", "sg"],
            "surabaya": ["sub"],
            "ho chi minh": ["hcm", "sgn"],
            "cape town": ["cpt"],
            "houston": ["hou"],
            "manila": ["mnl"],
            "busan": ["pus"],
            "jebel ali": ["jbl", "dxb"],
            "keelung": ["kel"],
            "yokohama": ["yok"],
            "hamburg": ["ham"],
            "chennai": ["maa", "madras"],
            "bangalore": ["blr"],
            "hyderabad": ["hyd"],
            "guangzhou": ["can", "gzg"],
            "shenzhen": ["szx", "szn"],
            "xingang": ["txg"],
            "tianjin": ["tsn"],
            "qingdao": ["tao"],
            "osaka": ["osa"],
            "genoa": ["goa"],
            "izmir": ["izm"],
            "ambarli": ["amr"],
            "laem chabang": ["lch"],
            "bangkok": ["bkk"],
            "nhava sheva": ["nsva", "nsh"],
            "mundra": ["mun"],
            "colombo": ["cmb"],
            "port klang": ["pkg", "klg"],
            "jeddah": ["jed"],  # Saudi ports
            "dammam": ["dam"],
            "riyadh": ["ruh"],
        }

        for full_name, abbrevs in abbreviations.items():
            if full_name in normalized_name:
                for abbrev in abbrevs:
                    name_to_code[abbrev] = code

    return code_to_name, name_to_code, code_to_all_names


def is_consolidated_inquiry(body: str) -> bool:
    """
    Detect consolidated rate inquiries: semicolon-separated multi-route requests.
    Pattern: "JED→MAA ICD 1.9 cbm; DAM→BLR ICD 600kg; RUH→HYD ICD 850kg"
    """
    return ";" in body and ("→" in body or "->" in body)


def get_consolidated_dest_order(body: str) -> List[str]:
    """
    Extract destination order from consolidated inquiry.
    Returns list like ['MAA', 'HYD', 'BLR'] based on email body.
    """
    order = []
    routes = body.split(";")
    for route in routes:
        # Find destination after arrow
        if "→" in route:
            dest_part = route.split("→")[1].strip().upper()
        elif "->" in route:
            dest_part = route.split("->")[1].strip().upper()
        else:
            continue

        # Extract port abbreviation (first 3 letters or known abbrev)
        abbrev_map = {'MAA': 'Chennai', 'BLR': 'Bangalore', 'HYD': 'Hyderabad'}
        for abbrev in abbrev_map:
            if abbrev in dest_part:
                order.append(abbrev_map[abbrev])
                break
    return order


def get_best_port_name(port_code: str, email_body: str, code_to_all_names: Dict[str, List[str]], is_destination: bool = False) -> Optional[str]:
    """
    Select the best port name from reference based on email context.
    - For consolidated inquiries, match the destination order from email
    - If email mentions specific "City ICD", prefer that exact match
    - Default to appropriate name based on context
    """
    if not port_code or port_code not in code_to_all_names:
        return None

    all_names = code_to_all_names[port_code]
    body_lower = email_body.lower()

    # Handle consolidated inquiries with combined names (DESTINATION ONLY)
    if is_consolidated_inquiry(email_body) and is_destination:
        dest_order = get_consolidated_dest_order(email_body)
        if len(dest_order) >= 2:
            # Build expected combined name pattern
            expected_pattern = " / ".join(
                [f"{city} ICD" for city in dest_order])
            # Look for matching combined name
            for name in all_names:
                if name == expected_pattern:
                    return name
            # Fallback: return any combined name that starts correctly
            combined_names = [n for n in all_names if " / " in n]
            if combined_names:
                return combined_names[0]

    # For ORIGINS: check for combined names when email mentions multiple ports
    if not is_destination:
        # Check for "or" pattern (e.g., "Shenzhen or Guangzhou")
        or_pattern = re.search(r'(\w+)\s+or\s+(\w+)', body_lower)
        if or_pattern:
            combined_names = [n for n in all_names if " / " in n]
            if combined_names:
                return combined_names[0]
        # Check for "/" pattern in origin (e.g., "Tianjin/Xingang")
        slash_pattern = re.search(r'(\w+)/(\w+)', body_lower)
        if slash_pattern:
            combined_names = [n for n in all_names if " / " in n]
            if combined_names:
                return combined_names[0]

    # Check for "to India" pattern - use "India (Chennai)" format
    if is_destination and port_code == "INMAA":
        if " to india" in body_lower and "icd" not in body_lower and "ppg" not in body_lower:
            india_chennai = [n for n in all_names if "india" in n.lower()]
            if india_chennai:
                return india_chennai[0]

    # Check if email mentions specific "City ICD" or "PPG" pattern (DESTINATION ONLY)
    # PPG (Paid Per Gateway) implies ICD destination
    if is_destination and ("icd" in body_lower or "ppg" in body_lower):
        # Map of city keywords to look for
        city_keywords = {
            'chennai': 'Chennai ICD',
            'bangalore': 'Bangalore ICD',
            'blr': 'Bangalore ICD',
            'hyderabad': 'Hyderabad ICD',
            'hyd': 'Hyderabad ICD',
            'mundra': 'Mundra ICD',
            'bangkok': 'Bangkok ICD',
            'whitefield': 'ICD Whitefield',
        }

        # Find which city ICD is mentioned
        for keyword, icd_name in city_keywords.items():
            # Check if email mentions this city with ICD
            if keyword in body_lower and 'icd' in body_lower:
                # Verify this name exists for the port code
                if icd_name in all_names:
                    return icd_name
                # Also check for reverse format (ICD City)
                reverse_name = f"ICD {icd_name.replace(' ICD', '')}"
                if reverse_name in all_names:
                    return reverse_name

        # Fallback: return first simple ICD name (not combined)
        simple_icd = [n for n in all_names if "icd" in n.lower()
                      and " / " not in n]
        if simple_icd:
            # Prefer "Chennai ICD" over "Bangalore ICD" for INMAA code
            chennai_icd = [n for n in simple_icd if 'chennai' in n.lower()]
            if chennai_icd:
                return chennai_icd[0]
            return simple_icd[0]

    # Default: return shortest simple name
    simple_names = [n for n in all_names if " / " not in n]
    if simple_names:
        return min(simple_names, key=len)

    return all_names[0]


def extract_weight_from_consolidated(body: str) -> Optional[float]:
    """
    Extract weight in kg from any route in a consolidated inquiry.
    Handles: "850kg", "600 kg", "750KG"
    """
    # Find all kg mentions
    kg_matches = re.findall(r'(\d+(?:,\d+)?(?:\.\d+)?)\s*kg', body.lower())
    if kg_matches:
        # Return first weight found (clean commas)
        weight_str = kg_matches[0].replace(',', '')
        return round(float(weight_str), 2)
    return None


def post_process_extraction(
    extracted: Dict,
    email_data: Dict,
    code_to_name: Dict[str, str],
    name_to_code: Dict[str, str],
    code_to_all_names: Dict[str, List[str]] = None
) -> Dict:
    """
    Post-process LLM extraction with deterministic business rules.
    Handles: product_line, rounding, ICD names, consolidated inquiries, weight extraction.
    """
    body = email_data.get("body", "")
    body_lower = body.lower()

    # 1. Determine product_line from port codes (deterministic)
    dest_code = extracted.get("destination_port_code", "")
    origin_code = extracted.get("origin_port_code", "")

    if dest_code and dest_code.startswith("IN"):
        extracted["product_line"] = "pl_sea_import_lcl"
    elif origin_code and origin_code.startswith("IN"):
        extracted["product_line"] = "pl_sea_export_lcl"
    else:
        # Default to import if unclear
        extracted["product_line"] = "pl_sea_import_lcl"

    # 2. Round numeric fields
    if extracted.get("cargo_weight_kg") is not None:
        extracted["cargo_weight_kg"] = round(
            float(extracted["cargo_weight_kg"]), 2)
    if extracted.get("cargo_cbm") is not None:
        extracted["cargo_cbm"] = round(float(extracted["cargo_cbm"]), 2)

    # 3. Handle RT units (Revenue Ton) - RT = CBM for LCL shipments
    rt_match = re.search(r'(\d+\.?\d*)\s*rt', body_lower)
    if rt_match:
        rt_value = float(rt_match.group(1))
        # RT = CBM for LCL shipments (if CBM not already set)
        if not extracted.get("cargo_cbm"):
            extracted["cargo_cbm"] = round(rt_value, 2)

    # 4. Handle consolidated inquiries - extract weight from any route
    if is_consolidated_inquiry(body):
        if not extracted.get("cargo_weight_kg"):
            weight = extract_weight_from_consolidated(body)
            if weight:
                extracted["cargo_weight_kg"] = weight

    # 5. Fix weight parsing for comma-separated numbers (e.g., "3,200 KGS")
    # Also look for weight with comma directly in body
    comma_weight_match = re.search(
        r'(\d{1,3}(?:,\d{3})+)\s*(?:kg|kgs)', body_lower)
    if comma_weight_match:
        weight_str = comma_weight_match.group(1).replace(',', '')
        extracted["cargo_weight_kg"] = round(float(weight_str), 2)
    elif extracted.get("cargo_weight_kg") is not None:
        weight = extracted["cargo_weight_kg"]
        # Check if weight seems too small (might be comma parsing issue)
        if weight < 10:
            # Look for larger weight pattern in body
            weight_match = re.search(r'(\d+)\s*(?:kg|kgs)', body_lower)
            if weight_match:
                parsed_weight = float(weight_match.group(1))
                if parsed_weight > weight * 100:  # Likely comma was misinterpreted
                    extracted["cargo_weight_kg"] = round(parsed_weight, 2)

    # 6. Set port names using context-aware selection - ALWAYS use best contextual name
    if extracted.get("origin_port_code") and code_to_all_names:
        origin_code = extracted["origin_port_code"]
        if origin_code in code_to_all_names:
            best_name = get_best_port_name(
                origin_code, body, code_to_all_names, is_destination=False)
            if best_name:
                extracted["origin_port_name"] = best_name
    elif not extracted.get("origin_port_code"):
        extracted["origin_port_name"] = None

    if extracted.get("destination_port_code") and code_to_all_names:
        dest_code = extracted["destination_port_code"]
        if dest_code in code_to_all_names:
            best_name = get_best_port_name(
                dest_code, body, code_to_all_names, is_destination=True)
            if best_name:
                extracted["destination_port_name"] = best_name
    elif not extracted.get("destination_port_code"):
        extracted["destination_port_name"] = None

    return extracted


def call_llm_and_parse(prompt: str, email_id: str, silent: bool = False) -> Dict:
    """
    Call LLM and parse JSON response with retry logic.
    Returns raw extracted data (before post-processing).

    Args:
        prompt: The prompt to send to LLM
        email_id: Email ID to add to result
        silent: If True, don't print debug messages

    Returns:
        Dict with extracted data (or null values on failure)
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )

            # Parse JSON response
            json_str = response.choices[0].message.content.strip()

            # Remove markdown code blocks if present
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                json_str = json_str.strip()

            extracted_data = json.loads(json_str)

            # Add email ID
            extracted_data["id"] = email_id
            return extracted_data

        except json.JSONDecodeError as e:
            if not silent:
                print(f"  JSON decode error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                if not silent:
                    print(
                        f"  Failed to parse JSON after {max_retries} attempts")
        except Exception as e:
            if not silent:
                print(f"  Error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                time.sleep(wait_time)
            else:
                if not silent:
                    print(f"  Failed after {max_retries} attempts")

    # Return null values on failure
    return {
        "id": email_id,
        "product_line": None,
        "origin_port_code": None,
        "origin_port_name": None,
        "destination_port_code": None,
        "destination_port_name": None,
        "incoterm": "FOB",
        "cargo_weight_kg": None,
        "cargo_cbm": None,
        "is_dangerous": False
    }


def extract_single_email(
    email_data: Dict,
    port_reference: List[Dict],
    code_to_name: Dict[str, str],
    name_to_code: Dict[str, str],
    code_to_all_names: Dict[str, List[str]]
) -> Dict:
    """
    Extract shipment details from one email using LLM.
    """
    # 1. Prepare prompt (select version)
    if PROMPT_VERSION == "v1":
        prompt = create_extraction_prompt_v1(
            email_data["subject"], email_data["body"], port_reference)
    elif PROMPT_VERSION == "v2":
        prompt = create_extraction_prompt_v2(
            email_data["subject"], email_data["body"], port_reference)
    else:
        prompt = create_extraction_prompt_v3(
            email_data["subject"], email_data["body"], port_reference)

    # 2. Call LLM and parse (using helper function)
    extracted_data = call_llm_and_parse(prompt, email_data["id"])

    # 3. Post-process
    extracted_data = post_process_extraction(
        extracted_data,
        email_data,
        code_to_name,
        name_to_code,
        code_to_all_names
    )

    # 4. Validate with Pydantic
    shipment = ShipmentExtraction(**extracted_data)

    # 5. Convert to dict for JSON output
    return shipment.model_dump()


def main():
    """Main function to process all emails."""
    # 1. Load input data
    print("Loading input data...")
    with open("emails_input.json", "r") as f:
        emails = json.load(f)

    with open("port_codes_reference.json", "r") as f:
        port_reference = json.load(f)

    # 2. Load port lookups
    code_to_name, name_to_code, code_to_all_names = load_port_reference()

    # 3. CHECK FOR EXISTING OUTPUT (RESUME LOGIC)
    results = []
    processed_ids = set()

    if os.path.exists("output.json"):
        try:
            with open("output.json", "r") as f:
                results = json.load(f)
                processed_ids = {r["id"] for r in results}
                print(
                    f"📂 Found existing output.json with {len(processed_ids)} emails")
                print(f"   Will resume from email {len(processed_ids) + 1}")
        except (json.JSONDecodeError, FileNotFoundError):
            print("⚠️  output.json exists but is invalid, starting fresh")
            results = []
            processed_ids = set()
    else:
        print("📝 Starting fresh - no existing output.json")

    # 4. Process each email (SKIP ALREADY PROCESSED)
    print(f"Processing {len(emails)} emails...")

    for i, email in enumerate(emails, 1):
        email_id = email['id']

        # SKIP if already processed
        if email_id in processed_ids:
            print(
                f"⏭️  Skipping {i}/{len(emails)}: {email_id} (already processed)")
            continue

        print(f"🔄 Processing {i}/{len(emails)}: {email_id}")

        try:
            result = extract_single_email(
                email,
                port_reference,
                code_to_name,
                name_to_code,
                code_to_all_names
            )
            results.append(result)

            # 💾 SAVE AFTER EACH EMAIL (so you don't lose progress!)
            with open("output.json", "w") as f:
                json.dump(results, f, indent=2)
            print(
                f"   ✅ Saved ({len(results)}/{len(emails)} emails processed)")

        except KeyboardInterrupt:
            print(
                f"\n⚠️  Interrupted! Progress saved to output.json ({len(results)} emails)")
            raise
        except Exception as e:
            print(f"   ❌ Error processing {email_id}: {e}")
            # Still save what we have
            with open("output.json", "w") as f:
                json.dump(results, f, indent=2)
            print(f"   💾 Progress saved ({len(results)} emails)")
            raise

        # Rate limiting: Wait 3 seconds between requests to avoid hitting limit
        if i < len(emails):
            time.sleep(3)

    print(f"\n✅ Done! Results saved to output.json")
    print(f"   Processed {len(results)} emails")


if __name__ == "__main__":
    main()
