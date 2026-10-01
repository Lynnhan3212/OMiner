import argparse
import json
from pathlib import Path

from src.services.evaluator import evaluate_cases, load_eval_cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Mini Opportunity Miner evaluation cases.")
    parser.add_argument("--cases", default="data/eval_cases.json")
    parser.add_argument("--output", default="outputs/eval_report.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_eval_cases(args.cases)
    summary = evaluate_cases(cases)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"total_cases: {summary['total_cases']}")
    print(f"passed_cases: {summary['passed_cases']}")
    print(f"failed_cases: {summary['failed_cases']}")
    print(f"skipped_cases: {summary['skipped_cases']}")
    print(f"top1_accuracy: {summary['top1_accuracy']:.2f}")
    print(f"average_recall_at_k: {summary['average_recall_at_k']:.2f}")
    print(f"average_precision_at_k: {summary['average_precision_at_k']:.2f}")
    print(f"average_quality_accuracy: {summary['average_quality_accuracy']:.2f}")
    print("domain_coverage:")
    for domain, coverage in summary["domain_coverage"].items():
        print(
            f"  {domain}: {coverage['coverage_status']}, "
            f"cases={coverage['total_cases']}, "
            f"human_reviewed={coverage['human_reviewed_cases']}, "
            f"draft={coverage['draft_cases']}, "
            f"needs_revision={coverage['needs_revision_cases']}"
        )
    print(f"report: {output_path}")


if __name__ == "__main__":
    main()
