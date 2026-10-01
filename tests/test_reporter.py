import sqlite3
from pathlib import Path

from src.nodes import reporter
from src.nodes.reporter import write_report
from src.schemas import (
    ApprovedGitHubSource,
    GitHubDiscoveryDiagnosis,
    GitHubEvidenceDiscovery,
    GitHubEvidenceSource,
    GitHubEvidenceSourceReview,
    GitHubIssueFetchResult,
    GitHubSearchAttempt,
    GitHubSearchExecutionResult,
    HumanConfirmation,
    NodeQualityRecord,
    QuerySpec,
    SignalDiagnosis,
    SignalSummary,
)
from tests.test_validator import valid_card


def test_reporter_writes_cards_and_markdown(tmp_path):
    state = write_report(
        {
            "run_id": "run_1",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [valid_card()],
            "valid_cards": [valid_card()],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "config": {"output_dir": str(tmp_path)},
        }
    )

    assert (tmp_path / "opportunity_cards.json").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report_zh.md").exists()
    assert state["output_cards_path"]
    assert state["report_path"]
    assert state["report_zh_path"]


def test_reporter_marks_running_state_as_success_in_markdown(tmp_path):
    write_report(
        {
            "run_id": "run_1",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [valid_card()],
            "valid_cards": [valid_card()],
            "validation_errors": [],
            "status": "running",
            "failure_reason": None,
            "config": {"output_dir": str(tmp_path)},
        }
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "- Status: success" in report


def test_reporter_writes_chinese_markdown_report(tmp_path):
    write_report(
        {
            "run_id": "run_1",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [valid_card()],
            "valid_cards": [valid_card()],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "config": {"output_dir": str(tmp_path)},
        }
    )

    report = (tmp_path / "report_zh.md").read_text(encoding="utf-8")
    assert "# Mini Opportunity Miner 中文报告" in report
    assert "## 运行摘要" in report
    assert "- 状态：success" in report
    assert "## 机会卡" in report
    assert "- 建议动作：" in report
    assert "- 用户痛点：" in report


def test_reporter_includes_route_and_diagnosis_sections(tmp_path):
    write_report(
        {
            "run_id": "run_diag",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [],
            "valid_cards": [],
            "validation_errors": [],
            "status": "partial",
            "failure_reason": None,
            "route_decision": "diagnose",
            "route_reason": "Average issue score 1.2 is below threshold 2.0.",
            "signal_summary": SignalSummary(
                valid_issue_count=10,
                average_score=1.2,
                high_signal_issue_count=1,
                signaled_issue_count=4,
                total_comments=3,
                total_reactions=0,
            ),
            "signal_diagnosis": SignalDiagnosis(
                diagnosis_id="diagnosis_001",
                status="low_signal",
                reason="Average issue score 1.2 is below threshold 2.0.",
                evidence_gaps=["Too few high-signal issues"],
                recommended_next_step="Collect more high-signal issues.",
            ),
            "quality_records": [
                NodeQualityRecord(
                    node_name="Signal Scorer",
                    quality_score=0.24,
                    quality_reason="Average score is weak.",
                    route_decision="diagnose",
                    route_reason="Average issue score is below threshold.",
                )
            ],
            "config": {"output_dir": str(tmp_path), "run_mode": "auto"},
        }
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")

    assert "Run mode: auto" in report
    assert "Route decision: diagnose" in report
    assert "Low-Signal Diagnosis" in report
    assert "Node Quality Summary" in report
    assert "运行模式：auto" in report_zh
    assert "路由决策：diagnose" in report_zh
    assert "平均 Issue 分数 1.2 低于阈值 2.0" in report_zh
    assert "低信号诊断" in report_zh
    assert "节点质量摘要" in report_zh


def test_reporter_includes_query_scope_details(tmp_path):
    write_report(
        {
            "run_id": "run_query",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [],
            "valid_cards": [],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "original_query": "Find browser agent developer-tool opportunities for independent developers",
            "query_spec": QuerySpec(
                query_id="query_001",
                original_query="Find browser agent developer-tool opportunities for independent developers",
                scope_status="in_scope",
                target_domain="browser agents",
                target_user="independent developers",
                opportunity_type="small tool, plugin, or SaaS",
                evidence_source="GitHub issues",
                included_keywords=["browser agent"],
                excluded_keywords=["documentation typo"],
                repo_scope=["browser-use/browser-use"],
                success_criteria="Find repeated pain.",
                human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
            ),
            "query_spec_path": "outputs/query_spec.json",
            "query_confirmation_status": "approved",
            "config": {"output_dir": str(tmp_path), "run_mode": "auto"},
        }
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")

    assert "## Query Scope" in report
    assert "Original query: Find browser agent" in report
    assert "Confirmation status: approved" in report
    assert "## 查询范围" in report_zh
    assert "确认状态：approved" in report_zh


def test_reporter_includes_github_discovery_and_input_sections(tmp_path):
    write_report(
        {
            "run_id": "run_github",
            "input_file": "data/generated/issues_github_discovery_001_20260830T121500Z.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [],
            "valid_cards": [],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "github_evidence_source_review": GitHubEvidenceSourceReview(
                discovery_id="github_discovery_001",
                status="approved",
                approved_sources=[ApprovedGitHubSource(repo="browser-use/browser-use", reason="Relevant")],
                confirmed_by="human",
            ),
            "github_evidence_source_review_path": "outputs/github_evidence_source_review.json",
            "github_fetch_result": GitHubIssueFetchResult(
                discovery_id="github_discovery_001",
                output_path="data/generated/issues_github_discovery_001_20260830T121500Z.json",
                fetched_count=30,
                skipped_pull_requests=2,
                skipped_invalid=1,
                comments_per_issue=2,
                approved_repos=["browser-use/browser-use"],
                rate_limit_remaining=58,
            ),
            "config": {"output_dir": str(tmp_path), "run_mode": "auto", "github_token": "ghp_secret"},
        }
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")

    assert "## GitHub Discovery" in report
    assert "Approved sources: browser-use/browser-use" in report
    assert "## GitHub Input" in report
    assert "Fetched issues: 30" in report
    assert "## GitHub 发现" in report_zh
    assert "已确认来源：browser-use/browser-use" in report_zh
    assert "## GitHub 输入" in report_zh
    assert "拉取 Issue 数：30" in report_zh
    assert "ghp_secret" not in report
    assert "ghp_secret" not in report_zh


def test_reporter_includes_github_source_quality_details(tmp_path):
    write_report(
        {
            "run_id": "run_github_quality",
            "input_file": "data/generated/issues.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [],
            "valid_cards": [],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "github_discovery": GitHubEvidenceDiscovery(
                discovery_id="github_discovery_001",
                query_id="query_001",
                search_queries=["browser agent is:issue"],
                candidates=[
                    GitHubEvidenceSource(
                        source_id="source_001",
                        repo="browser-use/browser-use",
                        repo_url="https://github.com/browser-use/browser-use",
                        matched_issue_urls=["https://github.com/browser-use/browser-use/issues/1"],
                        matched_issue_count=4,
                        open_issue_count=3,
                        stars=1000,
                        relevance_score=0.82,
                        query_relevance_score=0.8,
                        repo_relevance_score=0.6,
                        repo_relevance_reason="browser automation repo metadata matched",
                        repo_type="product_tool",
                        domain_fit_score=0.8,
                        product_repo_score=0.8,
                        source_quality_score=0.82,
                        evidence_quality="strong",
                        selection_reason="High recurrence and repo relevance",
                    ),
                    GitHubEvidenceSource(
                        source_id="source_002",
                        repo="owner/generic-agent",
                        repo_url="https://github.com/owner/generic-agent",
                        matched_issue_count=1,
                        open_issue_count=1,
                        relevance_score=0.2,
                        repo_relevance_score=0.0,
                        repo_relevance_reason="agent-only repo name without browser ecosystem match",
                        evidence_quality="weak",
                        selection_reason="Low repo relevance",
                    ),
                ],
                human_confirmation=HumanConfirmation(status="approved", confirmed_by="human"),
            ),
            "github_evidence_source_review": GitHubEvidenceSourceReview(
                discovery_id="github_discovery_001",
                status="approved",
                approved_sources=[ApprovedGitHubSource(repo="browser-use/browser-use", reason="Strong source")],
                confirmed_by="human",
            ),
            "config": {"output_dir": str(tmp_path), "run_mode": "auto"},
        }
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")

    assert "## Source Quality" in report
    assert "browser-use/browser-use: relevance 0.82, repo relevance 0.60, quality strong" in report
    assert "domain fit 0.80, product repo 0.80, repo type product_tool" in report
    assert "owner/generic-agent: relevance 0.20, repo relevance 0.00, quality weak" in report
    assert "## 来源质量" in report_zh
    assert "browser-use/browser-use：相关性 0.82，仓库相关性 0.60，证据质量 strong" in report_zh
    assert "领域匹配 0.80，产品仓库 0.80，仓库类型 product_tool" in report_zh
    assert "agent-only repo name without browser ecosystem match" in report_zh


def test_report_includes_github_discovery_diagnosis(tmp_path):
    write_report(
        {
            "run_id": "run_github_zero_candidates",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [],
            "valid_cards": [],
            "validation_errors": [],
            "status": "partial",
            "failure_reason": None,
            "github_discovery_diagnosis": GitHubDiscoveryDiagnosis(
                diagnosis_id="github_discovery_diagnosis_001",
                query_id="query_001",
                search_plan_id="query_search_plan_001",
                status="no_candidates",
                candidate_count=0,
                probable_causes=["Search terms were too narrow."],
                suggested_actions=["Broaden issue queries."],
            ),
            "github_discovery_diagnosis_path": "outputs/github_discovery_diagnosis.json",
            "config": {"output_dir": str(tmp_path), "run_mode": "auto"},
        }
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")

    assert "## GitHub Discovery Diagnosis" in report
    assert "Status: no_candidates" in report
    assert "Search terms were too narrow." in report
    assert "## GitHub 发现诊断" in report_zh
    assert "状态：no_candidates" in report_zh
    assert "Search terms were too narrow." in report_zh


def test_report_includes_github_search_trace_summary(tmp_path):
    write_report(
        {
            "run_id": "run_trace",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [],
            "valid_cards": [],
            "validation_errors": [],
            "status": "partial",
            "github_search_trace": GitHubSearchExecutionResult(
                query_attempts=[
                    GitHubSearchAttempt(stage="primary_issue", query="q1", status="success", result_count=0),
                    GitHubSearchAttempt(
                        stage="fallback_issue",
                        query="q2",
                        status="failed",
                        result_count=0,
                        error="rate limit",
                    ),
                ],
                fallback_used=True,
                warnings=["github fallback issue search failed for q2: rate limit"],
            ),
            "github_search_trace_path": "outputs/github_search_trace.json",
            "config": {"output_dir": str(tmp_path), "run_mode": "auto"},
        }
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")
    assert "## GitHub Search Trace" in report
    assert "fallback_issue" in report
    assert "## GitHub 搜索轨迹" in report_zh


def test_report_includes_pain_clustering_summary(tmp_path):
    final_state = write_report(
        {
            "run_id": "run_clustering_summary",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [valid_card()],
            "valid_cards": [valid_card()],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "pain_clustering_summary": {
                "method": "embedding",
                "threshold": 0.82,
                "min_spread": 0.74,
                "pain_points_before": 5,
                "pain_clusters_after": 2,
                "merged_group_count": 2,
                "fallback_used": False,
                "blocked_merge_count": 0,
                "warnings": [],
            },
            "config": {"output_dir": str(tmp_path), "mode": "mock"},
        }
    )

    report = Path(final_state["report_path"]).read_text(encoding="utf-8")
    report_zh = Path(final_state["report_zh_path"]).read_text(encoding="utf-8")
    assert "## Pain Clustering" in report
    assert "- Method: embedding" in report
    assert "- Pain points before clustering: 5" in report
    assert "## 痛点聚类" in report_zh
    assert "- 方法：embedding" in report_zh
    assert "- 聚类前痛点数：5" in report_zh


def test_chinese_report_includes_product_fields_beyond_pain(tmp_path):
    card = valid_card()
    write_report(
        {
            "run_id": "run_zh_detail",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [card],
            "valid_cards": [card],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "config": {"output_dir": str(tmp_path)},
        }
    )

    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")

    assert "- 目标用户：" in report_zh
    assert "- 频率信号：" in report_zh
    assert "- 当前替代方案：" in report_zh
    assert "- MVP 方案：" in report_zh
    assert "- 验证计划：" in report_zh
    assert "- 风险：" in report_zh
    assert "- 构建难度：中等（medium）" in report_zh


def test_mock_chinese_report_translates_opportunity_card_body(tmp_path):
    card = valid_card()
    write_report(
        {
            "run_id": "run_zh_translation",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [card],
            "valid_cards": [card],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "config": {"output_dir": str(tmp_path), "mode": "mock"},
            "llm_calls": 3,
        }
    )

    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")

    assert "导出可靠性工具" in report_zh
    assert "大文件导出任务失败" in report_zh
    assert "导出任务的重试和监控封装工具" in report_zh
    assert "建议动作：建议先验证（validate）" in report_zh
    assert "置信度：证据中等（medium）" in report_zh
    assert "Large export jobs fail" not in report_zh


def test_real_chinese_report_translation_increments_llm_call_count(tmp_path, monkeypatch):
    class FakeClient:
        def translate_opportunity_card_to_chinese(self, card):
            return {
                "title": "导出可靠性工具",
                "target_user": "生产报表团队",
                "pain": "大文件导出任务失败。",
                "frequency_signal": "多个 Issue 提到同类问题。",
                "current_workaround": "用户手动重试。",
                "mvp_idea": "导出任务重试和监控工具。",
                "monetization_hypothesis": "团队可能为可靠性自动化付费。",
                "validation_plan": "联系 Issue 作者验证。",
                "risk": "上游可能修复。",
                "assumptions": ["该问题足够重要。"],
            }

    monkeypatch.setattr(reporter, "get_llm_client", lambda config: FakeClient())

    final_state = write_report(
        {
            "run_id": "run_real_zh_translation",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [valid_card()],
            "valid_cards": [valid_card()],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "config": {"output_dir": str(tmp_path), "mode": "real"},
            "llm_calls": 3,
        }
    )

    assert final_state["llm_calls"] == 4


def test_real_chinese_report_translation_llm_calls_are_stored(tmp_path, monkeypatch):
    class FakeClient:
        def translate_opportunity_card_to_chinese(self, card):
            return {
                "title": "导出可靠性工具",
                "target_user": "生产报表团队",
                "pain": "大文件导出任务失败。",
                "frequency_signal": "多个 Issue 提到同类问题。",
                "current_workaround": "用户手动重试。",
                "mvp_idea": "导出任务重试和监控工具。",
                "monetization_hypothesis": "团队可能为可靠性自动化付费。",
                "validation_plan": "联系 Issue 作者验证。",
                "risk": "上游可能修复。",
                "assumptions": ["该问题足够重要。"],
            }

    db_path = tmp_path / "runs.sqlite"
    monkeypatch.setattr(reporter, "get_llm_client", lambda config: FakeClient())

    write_report(
        {
            "run_id": "run_real_zh_translation_store",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [valid_card()],
            "valid_cards": [valid_card()],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "config": {"output_dir": str(tmp_path), "mode": "real", "db_path": str(db_path)},
            "llm_calls": 3,
        }
    )

    with sqlite3.connect(db_path) as conn:
        llm_calls = conn.execute(
            "SELECT llm_calls FROM runs WHERE run_id = ?",
            ("run_real_zh_translation_store",),
        ).fetchone()[0]

    assert llm_calls == 4


def test_chinese_report_translates_common_internal_quality_reasons(tmp_path):
    write_report(
        {
            "run_id": "run_zh_quality",
            "input_file": "tests/fixtures/issues_valid.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [],
            "valid_cards": [],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "route_decision": "generate",
            "route_reason": "Signal thresholds passed.",
            "quality_records": [
                NodeQualityRecord(
                    node_name="Signal Scorer",
                    quality_score=1.0,
                    quality_reason="23 valid issues, 21 high-signal issues, average score 5.43.",
                    route_decision="generate",
                    route_reason="Signal thresholds passed.",
                )
            ],
            "config": {"output_dir": str(tmp_path), "mode": "mock", "run_mode": "auto"},
        }
    )

    report_zh = (tmp_path / "report_zh.md").read_text(encoding="utf-8")

    assert "信号质量达到生成阈值" in report_zh
    assert "23 个有效 Issue，21 个高信号 Issue，平均分 5.43" in report_zh
    assert "Signal thresholds passed" not in report_zh
    assert "valid issues" not in report_zh


def test_reporter_redacts_github_token_from_run_store(tmp_path):
    db_path = tmp_path / "runs.sqlite"
    write_report(
        {
            "run_id": "run_secret",
            "input_file": "data/issues.json",
            "valid_issues": [],
            "invalid_issues": [],
            "opportunity_cards": [],
            "valid_cards": [],
            "validation_errors": [],
            "status": "success",
            "failure_reason": None,
            "config": {
                "output_dir": str(tmp_path),
                "run_mode": "auto",
                "db_path": str(db_path),
                "github_token": "ghp_secret",
            },
        }
    )

    with sqlite3.connect(db_path) as conn:
        snapshot = conn.execute("SELECT config_snapshot FROM runs WHERE run_id = ?", ("run_secret",)).fetchone()[0]

    assert "ghp_secret" not in snapshot
    assert "***redacted***" in snapshot
