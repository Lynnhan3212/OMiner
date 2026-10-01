import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.ground_truth_promoter import promote_ground_truth_drafts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote accepted ground-truth drafts into eval cases.")
    parser.add_argument("--drafts", default="data/ground_truth_interpretation_draft.json")
    parser.add_argument("--output", default="data/generated/eval_cases_from_ground_truth.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    drafts_path = Path(args.drafts)
    output_path = Path(args.output)
    drafts = json.loads(drafts_path.read_text(encoding="utf-8"))
    eval_cases = promote_ground_truth_drafts(drafts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(eval_cases, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"drafts: {len(drafts)}")
    print(f"promoted_eval_cases: {len(eval_cases)}")
    print(f"output: {output_path}")


if __name__ == "__main__":
    main()
