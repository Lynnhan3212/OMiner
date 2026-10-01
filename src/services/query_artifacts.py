import json
from pathlib import Path
from typing import Any

from src.schemas import (
    QueryClarification,
    QueryClarificationResponse,
    QueryDecomposition,
    QueryIntakeReview,
    QuerySearchPlan,
    QuerySpec,
)


def _write_model(model: Any, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def write_query_spec(spec: QuerySpec, path: str | Path) -> Path:
    return _write_model(spec, path)


def write_query_intake_review(review: QueryIntakeReview, path: str | Path) -> Path:
    return _write_model(review, path)


def load_query_intake_review(path: str | Path) -> QueryIntakeReview | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return QueryIntakeReview(**json.loads(input_path.read_text(encoding="utf-8")))


def load_query_spec(path: str | Path) -> QuerySpec | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return QuerySpec(**json.loads(input_path.read_text(encoding="utf-8")))


def write_query_decomposition(decomposition: QueryDecomposition, path: str | Path) -> Path:
    return _write_model(decomposition, path)


def load_query_decomposition(path: str | Path) -> QueryDecomposition | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return QueryDecomposition(**json.loads(input_path.read_text(encoding="utf-8")))


def write_query_search_plan(plan: QuerySearchPlan, path: str | Path) -> Path:
    return _write_model(plan, path)


def load_query_search_plan(path: str | Path) -> QuerySearchPlan | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return QuerySearchPlan(**json.loads(input_path.read_text(encoding="utf-8")))


def write_query_clarification(clarification: QueryClarification, path: str | Path) -> Path:
    return _write_model(clarification, path)


def write_query_clarification_response_template(response: QueryClarificationResponse, path: str | Path) -> Path:
    return _write_model(response, path)


def load_query_clarification_response(path: str | Path) -> QueryClarificationResponse | None:
    input_path = Path(path)
    if not input_path.exists():
        return None
    return QueryClarificationResponse(**json.loads(input_path.read_text(encoding="utf-8")))
