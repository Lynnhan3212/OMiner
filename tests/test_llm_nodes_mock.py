from src.nodes.issue_reader import read_issues
from src.nodes.pain_clusterer import cluster_pain_points
from src.nodes.pain_extractor import extract_pain_points
from src.nodes.opportunity_generator import generate_opportunities
from src.nodes.signal_scorer import score_issues
from src.services.llm_client import get_llm_client
from tests.test_validator import valid_card


def test_mock_llm_nodes_produce_traceable_card():
    state = read_issues({"input_file": "tests/fixtures/issues_valid.json", "config": {"min_valid_issues": 10, "mode": "mock", "max_cards": 3}})
    state = score_issues(state)
    state = extract_pain_points(state)
    state = cluster_pain_points(state)
    state = generate_opportunities(state)

    assert state["pain_points"]
    assert state["pain_clusters"]
    assert state["opportunity_cards"][0].source_issue_ids
    assert state["opportunity_cards"][0].assumptions is not None
    assert state["llm_calls"] == 2
    assert state["pain_clustering_summary"]["method"] == "embedding"


def test_mock_clusterer_uses_semantic_clustering_by_default():
    state = read_issues(
        {
            "input_file": "tests/fixtures/issues_valid.json",
            "config": {
                "min_valid_issues": 10,
                "mode": "mock",
                "max_cards": 3,
                "semantic_clustering_enabled": True,
                "semantic_cluster_threshold": 0.82,
                "semantic_cluster_min_spread": 0.74,
                "embedding_model": "text-embedding-3-small",
                "embedding_batch_size": 64,
            },
        }
    )
    state = score_issues(state)
    state = extract_pain_points(state)
    state = cluster_pain_points(state)

    assert state["pain_clusters"]
    assert state["pain_clustering_summary"]["method"] == "embedding"
    assert state["pain_clustering_summary"]["fallback_used"] is False


def test_clusterer_can_disable_semantic_clustering():
    state = read_issues(
        {
            "input_file": "tests/fixtures/issues_valid.json",
            "config": {
                "min_valid_issues": 10,
                "mode": "mock",
                "max_cards": 3,
                "semantic_clustering_enabled": False,
            },
        }
    )
    state = score_issues(state)
    state = extract_pain_points(state)
    state = cluster_pain_points(state)

    assert state["pain_clustering_summary"]["method"] == "fallback_keyword"
    assert state["pain_clustering_summary"]["fallback_used"] is True


def test_mock_llm_translates_opportunity_card_for_chinese_report():
    client = get_llm_client({"mode": "mock"})

    translated = client.translate_opportunity_card_to_chinese(valid_card())

    assert translated["title"] == "导出可靠性工具"
    assert "大文件导出任务失败" in translated["pain"]
    assert "重试和监控" in translated["mvp_idea"]
