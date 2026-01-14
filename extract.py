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


def post_process_extraction(
    extracted: Dict,
    email_data: Dict,
    code_to_name: Dict[str, str],
    name_to_code: Dict[str, str],
    code_to_all_names: Dict[str, List[str]] = None
) -> Dict:
    """
    Post-process LLM extraction with deterministic business rules.
    Simple processing: product_line determination, rounding, canonical port names.
    """
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
    body_lower = email_data.get("body", "").lower()
    rt_match = re.search(r'(\d+\.?\d*)\s*rt', body_lower)
    if rt_match:
        rt_value = float(rt_match.group(1))
        # RT = CBM for LCL shipments (if CBM not already set)
        if not extracted.get("cargo_cbm"):
            extracted["cargo_cbm"] = round(rt_value, 2)

    # 4. Validate port names - only set canonical if LLM didn't extract a valid name
    # Check if LLM's port name is valid for the code (exists in reference)
    if extracted.get("origin_port_code"):
        origin_code = extracted["origin_port_code"]
        llm_origin_name = extracted.get("origin_port_name")

        if origin_code in code_to_name:
            # Check if LLM's name is valid for this code
            if code_to_all_names and origin_code in code_to_all_names:
                valid_names = [n.lower()
                               for n in code_to_all_names[origin_code]]
                if llm_origin_name and llm_origin_name.lower() in valid_names:
                    # LLM's name is valid, keep it
                    pass
                else:
                    # LLM's name is invalid or missing, use canonical
                    extracted["origin_port_name"] = code_to_name[origin_code]
            elif not llm_origin_name:
                # No name extracted, use canonical
                extracted["origin_port_name"] = code_to_name[origin_code]
    elif not extracted.get("origin_port_code"):
        extracted["origin_port_name"] = None

    if extracted.get("destination_port_code"):
        dest_code = extracted["destination_port_code"]
        llm_dest_name = extracted.get("destination_port_name")

        if dest_code in code_to_name:
            # Check if LLM's name is valid for this code
            if code_to_all_names and dest_code in code_to_all_names:
                valid_names = [n.lower() for n in code_to_all_names[dest_code]]
                if llm_dest_name and llm_dest_name.lower() in valid_names:
                    # LLM's name is valid, keep it
                    pass
                else:
                    # LLM's name is invalid or missing, use canonical
                    extracted["destination_port_name"] = code_to_name[dest_code]
            elif not llm_dest_name:
                # No name extracted, use canonical
                extracted["destination_port_name"] = code_to_name[dest_code]
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
