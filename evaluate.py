"""
Evaluation script to calculate accuracy metrics.
Compares output.json against ground_truth.json.
"""
import json
from typing import Any


def compare_field(predicted: Any, ground_truth: Any, field_name: str) -> bool:
    """Compare a single field value."""
    pred_val = predicted.get(field_name)
    truth_val = ground_truth.get(field_name)

    # Handle nulls
    if pred_val is None and truth_val is None:
        return True
    if pred_val is None or truth_val is None:
        return False

    # String comparison (case-insensitive, whitespace-trimmed)
    if isinstance(pred_val, str) and isinstance(truth_val, str):
        return pred_val.lower().strip() == truth_val.lower().strip()

    # Float comparison (with rounding to 2 decimals)
    if isinstance(pred_val, (int, float)) and isinstance(truth_val, (int, float)):
        return round(float(pred_val), 2) == round(float(truth_val), 2)

    # Boolean comparison
    if isinstance(pred_val, bool) and isinstance(truth_val, bool):
        return pred_val == truth_val

    return False


def evaluate():
    """Calculate and display accuracy metrics."""
    print("Loading files...")
    try:
        with open("output.json", "r") as f:
            predictions = json.load(f)
    except FileNotFoundError:
        print("Error: output.json not found. Run extract.py first.")
        return

    with open("ground_truth.json", "r") as f:
        ground_truth = json.load(f)

    # Create lookup by ID
    truth_dict = {item["id"]: item for item in ground_truth}

    # Fields to evaluate (excluding "id")
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

    # Calculate accuracy per field
    field_accuracies = {field: {"correct": 0, "total": 0} for field in fields}
    total_correct = 0
    total_fields = 0

    # Track which emails had errors
    email_errors = {field: [] for field in fields}

    for pred in predictions:
        email_id = pred["id"]
        truth = truth_dict.get(email_id, {})

        if not truth:
            print(f"Warning: No ground truth found for {email_id}")
            continue

        for field in fields:
            field_accuracies[field]["total"] += 1
            if compare_field(pred, truth, field):
                field_accuracies[field]["correct"] += 1
                total_correct += 1
            else:
                email_errors[field].append(email_id)
            total_fields += 1

    # Print results
    print("\n" + "="*60)
    print("ACCURACY METRICS")
    print("="*60)
    print(f"{'Field':<30} {'Accuracy':<15} {'Correct/Total'}")
    print("-"*60)

    for field, stats in field_accuracies.items():
        accuracy = (stats["correct"] / stats["total"]) * \
            100 if stats["total"] > 0 else 0
        print(
            f"{field:<30} {accuracy:>6.1f}%        {stats['correct']}/{stats['total']}")

    overall_accuracy = (total_correct / total_fields) * \
        100 if total_fields > 0 else 0
    print("-"*60)
    print(f"{'OVERALL ACCURACY':<30} {overall_accuracy:>6.1f}%        {total_correct}/{total_fields}")
    print("="*60)

    # Show emails with errors (top 5 per field)
    print("\n" + "="*60)
    print("EMAILS WITH ERRORS (Top 5 per field)")
    print("="*60)
    for field, error_emails in email_errors.items():
        if error_emails:
            accuracy = field_accuracies[field]["correct"] / \
                field_accuracies[field]["total"]
            if accuracy < 1.0:  # Only show if there are errors
                print(f"\n{field} ({len(error_emails)} errors):")
                for email_id in error_emails[:5]:
                    print(f"  - {email_id}")
                if len(error_emails) > 5:
                    print(f"  ... and {len(error_emails) - 5} more")


if __name__ == "__main__":
    evaluate()
