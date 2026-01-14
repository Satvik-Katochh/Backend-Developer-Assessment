"""
Single email tester - Shows raw LLM response, post-processing, and final accuracy.
Usage: python test_single_email.py EMAIL_001 [v1|v2|v3]
"""
import json
import os
import sys
from dotenv import load_dotenv
from prompts import create_extraction_prompt_v1, create_extraction_prompt_v2, create_extraction_prompt_v3
from evaluate import compare_field
from extract import post_process_extraction, load_port_reference, call_llm_and_parse

# Load environment variables (for extract.py's client initialization)
load_dotenv()


def get_field_details(predicted, ground_truth, field_name):
    """Get details for field comparison (uses evaluate.py logic)."""
    pred_val = predicted.get(field_name)
    truth_val = ground_truth.get(field_name)

    match = compare_field(predicted, ground_truth, field_name)

    if pred_val is None and truth_val is None:
        details = "Both null"
    elif pred_val is None or truth_val is None:
        details = f"Null: {pred_val} vs {truth_val}"
    else:
        details = f"{pred_val} vs {truth_val}"

    return match, details


def print_comparison_table(result, truth, title, max_width=100):
    """Print comparison table for a result - cleaner format."""
    fields = [
        "product_line",
        "origin_port_code",
        "origin_port_name",
        "destination_port_code",
        "destination_port_name",
        "incoterm",
        "cargo_weight_kg",
        "cargo_cbm",
        "is_dangerous"
    ]

    correct = 0
    total = len(fields)

    # Better column widths for readability
    field_width = 28
    value_width = 35
    status_width = 8

    print(f"\n{'Field':<{field_width}} {'Your Result':<{value_width}} {'Expected':<{value_width}} {'Status':<{status_width}}")
    print("─" * (field_width + value_width * 2 + status_width))

    for field in fields:
        match, details = get_field_details(
            result, truth, field) if truth else (False, "No ground truth")
        pred_val = result.get(field)
        truth_val = truth.get(field) if truth else "N/A"

        status = "✅ PASS" if match else "❌ FAIL"
        if match:
            correct += 1

        # Format values for display
        pred_display = str(pred_val) if pred_val is not None else "null"
        truth_display = str(truth_val) if truth_val is not None else "null"

        # Truncate long values but show more context
        if len(pred_display) > value_width - 2:
            pred_display = pred_display[:value_width - 5] + "..."
        if len(truth_display) > value_width - 2:
            truth_display = truth_display[:value_width - 5] + "..."

        print(f"{field:<{field_width}} {pred_display:<{value_width}} {truth_display:<{value_width}} {status:<{status_width}}")

    accuracy = (correct / total) * 100 if total > 0 else 0
    print("─" * (field_width + value_width * 2 + status_width))
    print(f"{'ACCURACY':<{field_width}} {accuracy:>6.1f}% ({correct}/{total} fields)")
    print("=" * (field_width + value_width * 2 + status_width))
    return accuracy


def main():
    """Test a single email."""
    # Get email ID and prompt version from command line
    if len(sys.argv) < 2:
        print("Usage: python test_single_email.py EMAIL_001 [v1|v2|v3]")
        print("\nExample:")
        print("  python test_single_email.py EMAIL_001")
        print("  python test_single_email.py EMAIL_007 v2")
        exit(1)

    email_id = sys.argv[1].upper()
    if not email_id.startswith("EMAIL_"):
        email_id = f"EMAIL_{email_id}"

    # Get prompt version (default: v2)
    prompt_version = sys.argv[2].lower() if len(sys.argv) > 2 else "v2"
    if prompt_version not in ["v1", "v2", "v3"]:
        print(f"⚠️  Invalid prompt version '{prompt_version}', using v2")
        prompt_version = "v2"

    print("\n" + "=" * 100)
    print(f"📧 TESTING: {email_id} | Prompt Version: {prompt_version.upper()}")
    print("=" * 100)

    # Load data
    with open("emails_input.json", "r") as f:
        all_emails = json.load(f)

    with open("port_codes_reference.json", "r") as f:
        port_reference = json.load(f)

    with open("ground_truth.json", "r") as f:
        ground_truth = json.load(f)

    # Find email
    email = next((e for e in all_emails if e["id"] == email_id), None)
    if not email:
        print(f"❌ Email {email_id} not found!")
        exit(1)

    truth = next((t for t in ground_truth if t["id"] == email_id), None)
    if not truth:
        print(f"⚠️  No ground truth for {email_id}")

    print(f"\nSubject: {email['subject']}")
    print(f"Body: {email['body'][:150]}...")
    print("\n" + "=" * 100)

    # Create prompt based on version
    if prompt_version == "v1":
        prompt = create_extraction_prompt_v1(
            email["subject"],
            email["body"],
            port_reference
        )
    elif prompt_version == "v2":
        prompt = create_extraction_prompt_v2(
            email["subject"],
            email["body"],
            port_reference
        )
    else:
        prompt = create_extraction_prompt_v3(
            email["subject"],
            email["body"],
            port_reference
        )

    print("\n🤖 STEP 1: Calling Groq API (Getting Raw LLM Response)...")
    print("=" * 100)

    try:
        # Use helper function from extract.py (DRY principle)
        raw_result = call_llm_and_parse(prompt, email_id, silent=True)

        # ==========================================
        # SHOW RAW LLM RESPONSE
        # ==========================================
        print("\n" + "─" * 100)
        print("📊 STEP 1: RAW LLM RESPONSE (Before Post-Processing)")
        print("─" * 100)

        raw_accuracy = print_comparison_table(
            raw_result, truth, "Raw LLM Response")

        print("\n📋 Raw LLM JSON:")
        print(json.dumps(raw_result, indent=2))

        # ==========================================
        # APPLY POST-PROCESSING
        # ==========================================
        print("\n" + "─" * 100)
        print("🔧 STEP 2: POST-PROCESSING")
        print("   Applying: Product Line Determination, Rounding, Port Canonicalization")
        print("─" * 100)

        # Load port lookups for post-processing
        code_to_name, name_to_code, code_to_all_names = load_port_reference()

        # Apply post-processing (same as extract.py does)
        final_result = post_process_extraction(
            raw_result.copy(),  # Don't modify original
            email,
            code_to_name,
            name_to_code,
            code_to_all_names
        )

        # ==========================================
        # SHOW FINAL PROCESSED RESULT
        # ==========================================
        print("\n" + "─" * 100)
        print("✅ STEP 3: FINAL RESULT (After Post-Processing)")
        print("   ⚠️  This is what goes into output.json (used for evaluation)")
        print("─" * 100)

        final_accuracy = print_comparison_table(
            final_result, truth, "Final Result")

        print("\n📋 Final Processed JSON:")
        print(json.dumps(final_result, indent=2))

        # ==========================================
        # SHOW WHAT CHANGED
        # ==========================================
        print("\n" + "─" * 100)
        print("🔄 STEP 4: POST-PROCESSING CHANGES")
        print("─" * 100)

        fields_changed = []
        for field in ["product_line", "origin_port_code", "origin_port_name",
                      "destination_port_code", "destination_port_name",
                      "cargo_weight_kg", "cargo_cbm", "incoterm"]:
            raw_val = raw_result.get(field)
            final_val = final_result.get(field)
            if raw_val != final_val:
                fields_changed.append(field)
                print(f"\n  📝 {field}:")
                print(f"     Raw LLM:     {raw_val}")
                print(f"     After PP:    {final_val}")

        if not fields_changed:
            print("\n  ✅ No changes - LLM response was already correct!")
        else:
            print(
                f"\n  📊 Summary: {len(fields_changed)} field(s) changed by post-processing")

        # ==========================================
        # SUMMARY
        # ==========================================
        print("\n" + "=" * 100)
        print("📈 ACCURACY SUMMARY")
        print("=" * 100)
        print(f"\n  Raw LLM Accuracy:     {raw_accuracy:>6.1f}%")
        print(f"  Final Accuracy:       {final_accuracy:>6.1f}%")
        improvement = final_accuracy - raw_accuracy
        if improvement > 0:
            print(f"  Improvement:          {improvement:>+6.1f}% ✅")
        elif improvement < 0:
            print(f"  Change:               {improvement:>+6.1f}% ⚠️")
        else:
            print(f"  Change:               {improvement:>+6.1f}% (no change)")

        print("\n" + "─" * 100)
        print("📋 GROUND TRUTH (Expected Result)")
        print("─" * 100)
        if truth:
            print(json.dumps(truth, indent=2))
        else:
            print("  ⚠️  No ground truth available")

        print("\n" + "=" * 100)
        print("✅ TESTING COMPLETE")
        print("=" * 100)
        print(
            f"\n💡 IMPORTANT: Final accuracy ({final_accuracy:.1f}%) is what matters!")
        print("   → This is what goes into output.json")
        print("   → This is what evaluate.py measures")
        print("   → This is what gets reported in README")

    except json.JSONDecodeError as e:
        print(f"\n❌ JSON Parse Error: {e}")
        print("  (Error occurred in call_llm_and_parse function)")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
