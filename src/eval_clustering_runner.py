import argparse
import json
from pathlib import Path

from src.services.clustering_evaluator import evaluate_clustering_cases, load_clustering_eval_cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Mini Opportunity Miner clustering evaluation cases.")
    parser.add_argument("--cases", default="data/eval_clustering_cases.json")
    parser.add_argument("--output", default="outputs/eval_clustering_report.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_clustering_eval_cases(args.cases)
    summary = evaluate_clustering_cases(cases, {"mode": "mock"})
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"total_cases: {summary['total_cases']}")
    print(f"passed_cases: {summary['passed_cases']}")
    print(f"failed_cases: {summary['failed_cases']}")
    print(f"average_duplicate_reduction_rate: {summary['average_duplicate_reduction_rate']:.2f}")
    print(f"average_over_merge_rate: {summary['average_over_merge_rate']:.2f}")
    print(f"average_expected_group_recall: {summary['average_expected_group_recall']:.2f}")
    print(f"report: {output_path}")


if __name__ == "__main__":
    main()
