from src.services.clustering_evaluator import evaluate_clustering_cases


def test_clustering_evaluator_scores_expected_groups():
    cases = [
        {
            "case_id": "cluster_rag_debugging_001",
            "domain": "rag",
            "pain_points": [
                {
                    "pain_id": "pain_001",
                    "source_issue_id": 1,
                    "evidence_url": "https://example.com/1",
                    "target_user": "RAG developers",
                    "pain": "Cannot debug bad retrieval.",
                    "scenario": "Debugging retrieval quality.",
                    "current_workaround": "Manual logs.",
                    "severity": "medium",
                },
                {
                    "pain_id": "pain_002",
                    "source_issue_id": 2,
                    "evidence_url": "https://example.com/2",
                    "target_user": "RAG developers",
                    "pain": "Retrieval debugging is unclear.",
                    "scenario": "Debugging retrieval quality.",
                    "current_workaround": "Manual logs.",
                    "severity": "high",
                },
                {
                    "pain_id": "pain_003",
                    "source_issue_id": 3,
                    "evidence_url": "https://example.com/3",
                    "target_user": "Calendar developers",
                    "pain": "Calendar sync fails.",
                    "scenario": "Syncing external calendars.",
                    "current_workaround": "Manual retry.",
                    "severity": "medium",
                },
            ],
            "expected_same_cluster": [["pain_001", "pain_002"]],
            "expected_separate": [["pain_001", "pain_003"]],
            "ground_truth_status": "draft",
        }
    ]

    summary = evaluate_clustering_cases(cases, {"mode": "mock"})

    assert summary["total_cases"] == 1
    assert summary["passed_cases"] == 1
    assert summary["average_expected_group_recall"] >= 0
    assert summary["average_over_merge_rate"] >= 0
    assert "duplicate_reduction_rate" in summary["results"][0]
