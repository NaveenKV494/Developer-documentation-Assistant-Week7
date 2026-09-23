import json
from pathlib import Path
import sys
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.judge import evaluate_with_judge



def compute_cohens_kappa(tp: int, tn: int, fp: int, fn: int) -> float:
    """Calculate Cohen's Kappa coefficient for inter-rater agreement."""
    total = tp + tn + fp + fn
    if total == 0:
        return 0.0

    observed_agreement = (tp + tn) / total

    # Marginal probabilities
    p_human_pos = (tp + fn) / total
    p_human_neg = (tn + fp) / total
    p_judge_pos = (tp + fp) / total
    p_judge_neg = (tn + fn) / total

    expected_agreement = (p_human_pos * p_judge_pos) + (p_human_neg * p_judge_neg)

    if expected_agreement == 1.0:
        return 1.0

    kappa = (observed_agreement - expected_agreement) / (1.0 - expected_agreement)
    return round(kappa, 4)


def validate_judge(
    validation_data_path: str | Path | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run human-vs-judge agreement validation on the calibration set.
    Proves the LLM judge agrees with human grading before trusting its scores.
    """
    if validation_data_path is None:
        validation_data_path = Path(__file__).parent / "data" / "judge_validation_set.json"

    data_file = Path(validation_data_path)
    if not data_file.exists():
        raise FileNotFoundError(f"Judge validation dataset not found: {data_file}")

    with open(data_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results = []
    tp = tn = fp = fn = 0

    if verbose:
        print(f"\n========================================================")
        print(f"       VALIDATING LLM JUDGE AGAINST HUMAN LABELS        ")
        print(f"========================================================")
        print(f"Calibrating on {len(cases)} human-annotated test cases...\n")

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    for i, item in enumerate(cases, 1):
        human_label = int(item["human_label"])
        judge_eval = evaluate_with_judge(
            question=item["question"],
            context=item["context"],
            answer=item["candidate_answer"],
        )

        judge_label = 1 if judge_eval.verdict == "PASS" else 0
        agrees = (human_label == judge_label)

        if human_label == 1 and judge_label == 1:
            tp += 1
            matrix_type = "TP"
        elif human_label == 0 and judge_label == 0:
            tn += 1
            matrix_type = "TN"
        elif human_label == 0 and judge_label == 1:
            fp += 1
            matrix_type = "FP"
        else:
            fn += 1
            matrix_type = "FN"

        results.append({
            "id": item.get("id", f"CALIB_{i}"),
            "question": item["question"][:50] + "...",
            "human_label": human_label,
            "judge_label": judge_label,
            "judge_score": judge_eval.score,
            "judge_verdict": judge_eval.verdict,
            "agrees": agrees,
            "matrix_type": matrix_type,
            "reasoning": judge_eval.reasoning,
        })

        if verbose:
            icon = "[AGREE]" if agrees else "[DISAGREE]"
            print(f"[{i:02d}/{len(cases):02d}] {item['id']}: Human={human_label} | Judge={judge_label} ({judge_eval.verdict}) -> {icon} ({matrix_type})")

    total = len(cases)
    agreement_rate = (tp + tn) / total if total > 0 else 0.0
    kappa = compute_cohens_kappa(tp, tn, fp, fn)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    is_validated = (agreement_rate >= 0.83 and kappa >= 0.65)

    summary = {
        "total_cases": total,
        "true_positives": tp,
        "true_negatives": tn,
        "false_positives": fp,
        "false_negatives": fn,
        "agreement_rate": round(agreement_rate, 4),
        "cohens_kappa": kappa,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "is_validated": is_validated,
        "results": results,
    }

    if verbose:
        print(f"\n---------------- JUDGE VALIDATION METRICS ----------------")
        print(f"Total Calibration Cases : {total}")
        print(f"Observed Agreement Rate : {agreement_rate * 100:.1f}% ({tp + tn}/{total})")
        print(f"Cohen's Kappa (kappa)   : {kappa:.4f}")
        print(f"Confusion Matrix        : TP={tp}, TN={tn}, FP={fp}, FN={fn}")
        print(f"Precision / Recall / F1 : {precision:.3f} / {recall:.3f} / {f1:.3f}")
        print(f"Judge Status            : {'VALIDATED (Reliable)' if is_validated else 'UNVALIDATED (Needs tuning)'}")
        print(f"----------------------------------------------------------\n")


    return summary


if __name__ == "__main__":
    validate_judge()
