import json
import re
from datetime import UTC, datetime
from pathlib import Path

from src.schemas import RunEvent, RunSummary
from src.services.llm_client import get_llm_client
from src.services.run_store import RunStore
from src.state import AgentState


def _dump_card(card):
    return card.model_dump() if hasattr(card, "model_dump") else card


def _decision_zh(decision: str) -> str:
    return {
        "build": "可以原型构建",
        "validate": "建议先验证",
        "watch": "继续观察",
        "reject": "暂不建议做",
    }.get(decision, "未知")


def _decision_display_zh(decision: str) -> str:
    return f"{_decision_zh(decision)}（{decision}）"


def _confidence_zh(confidence: str) -> str:
    return {
        "high": "证据较强",
        "medium": "证据中等",
        "low": "证据较弱",
    }.get(confidence, "未知")


def _confidence_display_zh(confidence: str) -> str:
    return f"{_confidence_zh(confidence)}（{confidence}）"


def _difficulty_zh(difficulty: str) -> str:
    return {
        "high": "高",
        "medium": "中等",
        "low": "低",
    }.get(difficulty, "未知")


def _difficulty_display_zh(difficulty: str) -> str:
    return f"{_difficulty_zh(difficulty)}（{difficulty}）"


def _diagnostic_text_zh(text: str | None) -> str:
    if not text:
        return "无"
    exact = {
        "Signal thresholds passed.": "信号质量达到生成阈值。",
        "Average score is weak.": "平均分较弱。",
        "Average issue score is below threshold.": "平均 Issue 分数低于阈值。",
        "Too few high-signal issues": "高信号 Issue 数量不足",
        "Collect more high-signal issues.": "补充更多高信号 Issue。",
        "Collect more issues before generating cards.": "先补充更多 Issue，再生成机会卡。",
    }
    if text in exact:
        return exact[text]

    average_match = re.fullmatch(r"Average issue score ([\d.]+) is below threshold ([\d.]+)\.", text)
    if average_match:
        return f"平均 Issue 分数 {average_match.group(1)} 低于阈值 {average_match.group(2)}。"

    quality_match = re.fullmatch(
        r"(\d+) valid issues, (\d+) high-signal issues, average score ([\d.]+)\.",
        text,
    )
    if quality_match:
        return (
            f"{quality_match.group(1)} 个有效 Issue，"
            f"{quality_match.group(2)} 个高信号 Issue，平均分 {quality_match.group(3)}。"
        )
    return text


def _safe_config_snapshot(config: dict) -> str:
    safe_config = dict(config)
    if "github_token" in safe_config:
        safe_config["github_token"] = "***redacted***" if safe_config["github_token"] else None
    if "llm_api_key" in safe_config:
        safe_config["llm_api_key"] = "***redacted***" if safe_config["llm_api_key"] else None
    return json.dumps(safe_config, ensure_ascii=False)


def _build_chinese_cards(cards, config: dict) -> tuple[list[dict], int]:
    client = get_llm_client(config)
    translated_cards = []
    for card in cards:
        translated_cards.append(client.translate_opportunity_card_to_chinese(card))
    return translated_cards, len(translated_cards) if config.get("mode") == "real" else 0


def write_report(state: AgentState) -> AgentState:
    config = state.get("config", {})
    output_dir = Path(config.get("output_dir", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)

    cards = state.get("valid_cards", state.get("opportunity_cards", []))
    output_cards_path = output_dir / "opportunity_cards.json"
    report_path = output_dir / "report.md"
    report_zh_path = output_dir / "report_zh.md"
    diagnosis_path = output_dir / "diagnosis.json"
    diagnosis_zh_path = output_dir / "diagnosis_zh.md"
    final_status = state.get("status", "success")
    if final_status == "running":
        final_status = "success"

    output_cards_path.write_text(
        json.dumps([_dump_card(card) for card in cards], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    validation_errors = state.get("validation_errors", [])
    signal_summary = state.get("signal_summary")
    signal_diagnosis = state.get("signal_diagnosis")
    quality_records = state.get("quality_records", [])
    query_spec = state.get("query_spec")
    query_clarification = state.get("query_clarification")
    github_discovery = state.get("github_discovery")
    github_discovery_diagnosis = state.get("github_discovery_diagnosis")
    github_review = state.get("github_evidence_source_review")
    github_search_trace = state.get("github_search_trace")
    github_fetch = state.get("github_fetch_result")
    if github_fetch:
        (output_dir / "github_issue_fetch_result.json").write_text(
            json.dumps(github_fetch.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8",
        )
    clustering = state.get("pain_clustering_summary")
    cards_zh, translation_llm_calls = _build_chinese_cards(cards, config)
    report = [
        "# Mini Opportunity Miner Report",
        "",
        "## Run Summary",
        f"- Status: {final_status}",
        f"- Failure reason: {state.get('failure_reason') or 'none'}",
        f"- Valid issues: {len(state.get('valid_issues', []))}",
        f"- Invalid issues: {len(state.get('invalid_issues', []))}",
        f"- Valid cards: {len(state.get('valid_cards', cards))}",
    ]
    if config.get("run_mode"):
        report.append(f"- Run mode: {config.get('run_mode')}")
    if state.get("route_decision"):
        report.append(f"- Route decision: {state.get('route_decision')}")
    if state.get("route_reason"):
        report.append(f"- Route reason: {state.get('route_reason')}")

    if state.get("original_query") or query_spec or query_clarification:
        report.extend(["", "## Query Scope"])
        if state.get("original_query"):
            report.append(f"- Original query: {state.get('original_query')}")
        if query_spec:
            report.extend(
                [
                    f"- Scope status: {query_spec.scope_status}",
                    f"- Target domain: {query_spec.target_domain}",
                    f"- Target user: {query_spec.target_user}",
                    f"- Opportunity type: {query_spec.opportunity_type}",
                    f"- Confirmation status: {query_spec.human_confirmation.status}",
                    f"- Query spec path: {state.get('query_spec_path') or 'none'}",
                ]
            )
        if query_clarification:
            report.extend(
                [
                    f"- Scope status: {query_clarification.scope_status}",
                    f"- Reason: {query_clarification.reason}",
                    f"- Clarifying questions: {', '.join(query_clarification.clarifying_questions)}",
                    f"- Clarification response path: {state.get('query_clarification_response_path') or 'none'}",
                ]
            )

    if github_review:
        approved_repos = ", ".join(source.repo for source in github_review.approved_sources) or "none"
        rejected_repos = ", ".join(
            f"{source.repo} ({source.reason})" for source in github_review.rejected_sources
        ) or "none"
        report.extend(
            [
                "",
                "## GitHub Discovery",
                f"- Discovery status: {github_review.status}",
                f"- Approved sources: {approved_repos}",
                f"- Rejected sources: {rejected_repos}",
                f"- Review path: {state.get('github_evidence_source_review_path') or 'none'}",
            ]
        )
    if github_discovery and github_discovery.candidates:
        report.extend(["", "## Source Quality"])
        for source in github_discovery.candidates:
            report.append(
                f"- {source.repo}: relevance {source.relevance_score:.2f}, "
                f"repo relevance {source.repo_relevance_score:.2f}, quality {source.evidence_quality}, "
                f"domain fit {source.domain_fit_score:.2f}, product repo {source.product_repo_score:.2f}, "
                f"repo type {source.repo_type}, noise flags {', '.join(source.noise_flags) or 'none'}; "
                f"{source.repo_relevance_reason}; {source.selection_reason}"
            )
    if github_discovery_diagnosis:
        report.extend(
            [
                "",
                "## GitHub Discovery Diagnosis",
                f"- Status: {github_discovery_diagnosis.status}",
                f"- Candidate count: {github_discovery_diagnosis.candidate_count}",
                f"- Diagnosis path: {state.get('github_discovery_diagnosis_path') or 'none'}",
                f"- Probable causes: {', '.join(github_discovery_diagnosis.probable_causes) if github_discovery_diagnosis.probable_causes else 'none'}",
                f"- Suggested actions: {', '.join(github_discovery_diagnosis.suggested_actions) if github_discovery_diagnosis.suggested_actions else 'none'}",
            ]
        )
    if github_search_trace:
        report.extend(["", "## GitHub Search Trace"])
        report.append(f"- Trace path: {state.get('github_search_trace_path') or 'none'}")
        report.append(f"- Fallback used: {'yes' if github_search_trace.fallback_used else 'no'}")
        report.append(
            f"- Repo-hint scoped search used: {'yes' if github_search_trace.repo_hint_scoped_search_used else 'no'}"
        )
        report.append(
            f"- Repo-scoped expansion used: {'yes' if github_search_trace.repo_scoped_expansion_used else 'no'}"
        )
        for attempt in github_search_trace.query_attempts[:10]:
            report.append(
                f"- {attempt.stage}: {attempt.status}, results={attempt.result_count}, query={attempt.query}"
            )
    if github_fetch:
        report.extend(
            [
                "",
                "## GitHub Input",
                f"- Generated input file: {github_fetch.output_path}",
                f"- Fetched issues: {github_fetch.fetched_count}",
                f"- Search matches collected: {github_fetch.matched_fetched_count}",
                f"- Checked supplements admitted: {github_fetch.supplemental_fetched_count}",
                "- Collection audit: github_issue_fetch_result.json (includes rejected supplements and failures)",
                f"- Skipped pull requests: {github_fetch.skipped_pull_requests}",
                f"- Skipped invalid issues: {github_fetch.skipped_invalid}",
                f"- Comments per issue: {github_fetch.comments_per_issue}",
                f"- Rate limit remaining: {github_fetch.rate_limit_remaining if github_fetch.rate_limit_remaining is not None else 'unknown'}",
            ]
        )
        report.extend(f"- Collection warning ({w.repo}): {w.message}" for w in github_fetch.warnings)
        report.append("- Closed issues are historical evidence only; open status also does not prove current unmet demand.")
        report.extend(
            f"- {issue.url}: state={issue.state}, reason={issue.state_reason or 'unknown'}, "
            f"origin={issue.collection_origin}, relevance={issue.relevance_status}, comments={issue.comments_status}"
            for issue in state.get("valid_issues", [])
        )
    if clustering:
        report.extend(
            [
                "",
                "## Pain Clustering",
                f"- Method: {clustering.get('method')}",
                f"- Threshold: {clustering.get('threshold')}",
                f"- Min spread: {clustering.get('min_spread')}",
                f"- Pain points before clustering: {clustering.get('pain_points_before')}",
                f"- Pain clusters after clustering: {clustering.get('pain_clusters_after')}",
                f"- Merged duplicate/similar pain groups: {clustering.get('merged_group_count')}",
                f"- Fallback used: {'yes' if clustering.get('fallback_used') else 'no'}",
            ]
        )
        warnings = clustering.get("warnings") or []
        if warnings:
            report.append(f"- Warnings: {', '.join(warnings)}")

    if signal_summary:
        report.extend(
            [
                "",
                "## Signal Summary",
                f"- Valid issue count: {signal_summary.valid_issue_count}",
                f"- Average score: {signal_summary.average_score}",
                f"- High-signal issues: {signal_summary.high_signal_issue_count}",
                f"- Signaled issues: {signal_summary.signaled_issue_count}",
                f"- Total comments: {signal_summary.total_comments}",
                f"- Total reactions: {signal_summary.total_reactions}",
            ]
        )
    if signal_diagnosis:
        report.extend(
            [
                "",
                "## Low-Signal Diagnosis",
                f"- Status: {signal_diagnosis.status}",
                f"- Reason: {signal_diagnosis.reason}",
                f"- Evidence gaps: {', '.join(signal_diagnosis.evidence_gaps) if signal_diagnosis.evidence_gaps else 'none'}",
                f"- Recommended next step: {signal_diagnosis.recommended_next_step}",
            ]
        )
    if quality_records:
        report.extend(["", "## Node Quality Summary"])
        for quality in quality_records:
            report.append(f"- {quality.node_name}: {quality.quality_score:.2f} - {quality.quality_reason}")

    report.extend(["", "## Opportunity Cards"])
    for card in cards:
        report.extend(
            [
                "",
                f"### {card.title}",
                f"- Decision: {card.decision}",
                f"- Confidence: {card.confidence}",
                f"- Pain: {card.pain}",
                f"- Evidence: {', '.join(card.evidence_urls)}",
                f"- Current unmet need: {card.current_need_status}",
                f"- Evidence states: {', '.join(ref.url + ' [' + ref.state + ']' for ref in card.evidence_context) or 'unknown'}",
                f"- Assumptions: {', '.join(card.assumptions) if card.assumptions else 'none'}",
            ]
        )
    if validation_errors:
        report.extend(["", "## Validation Errors"])
        for error in validation_errors:
            report.append(f"- {error.card_id or 'unknown'} {error.field}: {error.message}")

    report_path.write_text("\n".join(report), encoding="utf-8")

    report_zh = [
        "# Mini Opportunity Miner 中文报告",
        "",
        "## 运行摘要",
        f"- 状态：{final_status}",
        f"- 失败原因：{state.get('failure_reason') or '无'}",
        f"- 有效 Issue 数：{len(state.get('valid_issues', []))}",
        f"- 无效 Issue 数：{len(state.get('invalid_issues', []))}",
        f"- 有效机会卡数：{len(state.get('valid_cards', cards))}",
    ]
    if config.get("run_mode"):
        report_zh.append(f"- 运行模式：{config.get('run_mode')}")
    if state.get("route_decision"):
        report_zh.append(f"- 路由决策：{state.get('route_decision')}")
    if state.get("route_reason"):
        report_zh.append(f"- 路由原因：{_diagnostic_text_zh(state.get('route_reason'))}")

    if state.get("original_query") or query_spec or query_clarification:
        report_zh.extend(["", "## 查询范围"])
        if state.get("original_query"):
            report_zh.append(f"- 原始问题：{state.get('original_query')}")
        if query_spec:
            report_zh.extend(
                [
                    f"- 范围状态：{query_spec.scope_status}",
                    f"- 目标领域：{query_spec.target_domain}",
                    f"- 目标用户：{query_spec.target_user}",
                    f"- 机会类型：{query_spec.opportunity_type}",
                    f"- 确认状态：{query_spec.human_confirmation.status}",
                    f"- Query spec 路径：{state.get('query_spec_path') or '无'}",
                ]
            )
        if query_clarification:
            report_zh.extend(
                [
                    f"- 范围状态：{query_clarification.scope_status}",
                    f"- 原因：{query_clarification.reason}",
                    f"- 需要澄清的问题：{', '.join(query_clarification.clarifying_questions)}",
                    f"- 澄清回复路径：{state.get('query_clarification_response_path') or '无'}",
                ]
            )

    if github_review:
        approved_repos = ", ".join(source.repo for source in github_review.approved_sources) or "无"
        rejected_repos = ", ".join(
            f"{source.repo}（{source.reason}）" for source in github_review.rejected_sources
        ) or "无"
        report_zh.extend(
            [
                "",
                "## GitHub 发现",
                f"- 发现状态：{github_review.status}",
                f"- 已确认来源：{approved_repos}",
                f"- 已拒绝来源：{rejected_repos}",
                f"- Review 文件路径：{state.get('github_evidence_source_review_path') or '无'}",
            ]
        )
    if github_discovery and github_discovery.candidates:
        report_zh.extend(["", "## 来源质量"])
        for source in github_discovery.candidates:
            report_zh.append(
                f"- {source.repo}：相关性 {source.relevance_score:.2f}，"
                f"仓库相关性 {source.repo_relevance_score:.2f}，证据质量 {source.evidence_quality}，"
                f"领域匹配 {source.domain_fit_score:.2f}，产品仓库 {source.product_repo_score:.2f}，"
                f"仓库类型 {source.repo_type}，噪声标记 {', '.join(source.noise_flags) or '无'}；"
                f"{source.repo_relevance_reason}；{source.selection_reason}"
            )
    if github_discovery_diagnosis:
        report_zh.extend(
            [
                "",
                "## GitHub 发现诊断",
                f"- 状态：{github_discovery_diagnosis.status}",
                f"- 候选来源数：{github_discovery_diagnosis.candidate_count}",
                f"- 诊断文件路径：{state.get('github_discovery_diagnosis_path') or '无'}",
                f"- 可能原因：{', '.join(github_discovery_diagnosis.probable_causes) if github_discovery_diagnosis.probable_causes else '无'}",
                f"- 建议动作：{', '.join(github_discovery_diagnosis.suggested_actions) if github_discovery_diagnosis.suggested_actions else '无'}",
            ]
        )
    if github_search_trace:
        report_zh.extend(["", "## GitHub 搜索轨迹"])
        report_zh.append(f"- 轨迹文件路径：{state.get('github_search_trace_path') or '无'}")
        report_zh.append(f"- 是否使用 fallback：{'是' if github_search_trace.fallback_used else '否'}")
        report_zh.append(
            f"- 是否使用 repo hint 定向搜索：{'是' if github_search_trace.repo_hint_scoped_search_used else '否'}"
        )
        report_zh.append(
            f"- 是否使用 repo-scoped 扩展：{'是' if github_search_trace.repo_scoped_expansion_used else '否'}"
        )
        for attempt in github_search_trace.query_attempts[:10]:
            report_zh.append(
                f"- {attempt.stage}：{attempt.status}，结果数={attempt.result_count}，query={attempt.query}"
            )
    if github_fetch:
        report_zh.extend(
            [
                "",
                "## GitHub 输入",
                f"- 生成的数据文件：{github_fetch.output_path}",
                f"- 拉取 Issue 数：{github_fetch.fetched_count}",
                f"- 命中链接采集数：{github_fetch.matched_fetched_count}",
                f"- 相关性初筛通过的补采数：{github_fetch.supplemental_fetched_count}",
                "- 采集审计：github_issue_fetch_result.json（包含未通过补采及失败记录）",
                f"- 跳过 PR 数：{github_fetch.skipped_pull_requests}",
                f"- 跳过无效 Issue 数：{github_fetch.skipped_invalid}",
                f"- 每个 Issue 评论数上限：{github_fetch.comments_per_issue}",
                f"- 剩余额度：{github_fetch.rate_limit_remaining if github_fetch.rate_limit_remaining is not None else '未知'}",
            ]
        )
        report_zh.extend(f"- 采集警告（{w.repo}）：{w.message}" for w in github_fetch.warnings)
        report_zh.append("- closed 仅为历史证据；open 状态也不能证明当前仍有未解决需求。补采词项匹配不等于人工相关性确认。")
        report_zh.extend(
            f"- {issue.url}：状态={issue.state}，关闭原因={issue.state_reason or '未知'}，"
            f"来源={issue.collection_origin}，相关性={issue.relevance_status}，评论={issue.comments_status}"
            for issue in state.get("valid_issues", [])
        )
    if clustering:
        report_zh.extend(
            [
                "",
                "## 痛点聚类",
                f"- 方法：{clustering.get('method')}",
                f"- 阈值：{clustering.get('threshold')}",
                f"- 最小组内相似度：{clustering.get('min_spread')}",
                f"- 聚类前痛点数：{clustering.get('pain_points_before')}",
                f"- 聚类后痛点簇数：{clustering.get('pain_clusters_after')}",
                f"- 合并的重复/相似痛点组数：{clustering.get('merged_group_count')}",
                f"- 是否使用 fallback：{'是' if clustering.get('fallback_used') else '否'}",
            ]
        )
        warnings = clustering.get("warnings") or []
        if warnings:
            report_zh.append(f"- 警告：{', '.join(warnings)}")

    if signal_summary:
        report_zh.extend(
            [
                "",
                "## 信号摘要",
                f"- 有效 Issue 数：{signal_summary.valid_issue_count}",
                f"- 平均分：{signal_summary.average_score}",
                f"- 高信号 Issue 数：{signal_summary.high_signal_issue_count}",
                f"- 有信号 Issue 数：{signal_summary.signaled_issue_count}",
                f"- 评论总数：{signal_summary.total_comments}",
                f"- 反应总数：{signal_summary.total_reactions}",
            ]
        )
    if signal_diagnosis:
        report_zh.extend(
            [
                "",
                "## 低信号诊断",
                f"- 状态：{signal_diagnosis.status}",
                f"- 原因：{_diagnostic_text_zh(signal_diagnosis.reason)}",
                f"- 证据缺口：{', '.join(_diagnostic_text_zh(gap) for gap in signal_diagnosis.evidence_gaps) if signal_diagnosis.evidence_gaps else '无'}",
                f"- 建议下一步：{_diagnostic_text_zh(signal_diagnosis.recommended_next_step)}",
            ]
        )
    if quality_records:
        report_zh.extend(["", "## 节点质量摘要"])
        for quality in quality_records:
            report_zh.append(f"- {quality.node_name}：{quality.quality_score:.2f} - {_diagnostic_text_zh(quality.quality_reason)}")

    report_zh.extend(["", "## 机会卡"])
    for card, card_zh in zip(cards, cards_zh, strict=False):
        report_zh.extend(
            [
                "",
                f"### {card_zh['title']}",
                f"- 建议动作：{_decision_display_zh(card.decision)}",
                f"- 置信度：{_confidence_display_zh(card.confidence)}",
                f"- 目标用户：{card_zh['target_user']}",
                f"- 用户痛点：{card_zh['pain']}",
                f"- 频率信号：{card_zh['frequency_signal']}",
                f"- 当前替代方案：{card_zh['current_workaround']}",
                f"- MVP 方案：{card_zh['mvp_idea']}",
                f"- 构建难度：{_difficulty_display_zh(card.build_difficulty)}",
                f"- 商业化假设：{card_zh['monetization_hypothesis']}",
                f"- 验证计划：{card_zh['validation_plan']}",
                f"- 风险：{card_zh['risk']}",
                f"- 证据链接：{', '.join(card.evidence_urls)}",
                "- 当前未解决需求：尚未验证（unverified）",
                f"- 证据状态：{', '.join(ref.url + ' [' + ref.state + ']' for ref in card.evidence_context) or '未知'}",
                f"- 未验证假设：{', '.join(card_zh['assumptions']) if card_zh['assumptions'] else '无'}",
            ]
        )
    if validation_errors:
        report_zh.extend(["", "## 校验错误"])
        for error in validation_errors:
            report_zh.append(f"- {error.card_id or 'unknown'} {error.field}：{error.message}")

    report_zh_path.write_text("\n".join(report_zh), encoding="utf-8")

    final_state: AgentState = {
        **state,
        "output_cards_path": str(output_cards_path),
        "report_path": str(report_path),
        "report_zh_path": str(report_zh_path),
        "llm_calls": state.get("llm_calls", 0) + translation_llm_calls,
    }
    if signal_diagnosis:
        diagnosis_path.write_text(
            json.dumps(signal_diagnosis.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        diagnosis_zh = [
            "# 低信号诊断",
            "",
            f"- 状态：{signal_diagnosis.status}",
            f"- 原因：{_diagnostic_text_zh(signal_diagnosis.reason)}",
            f"- 证据缺口：{', '.join(_diagnostic_text_zh(gap) for gap in signal_diagnosis.evidence_gaps) if signal_diagnosis.evidence_gaps else '无'}",
            f"- 建议下一步：{_diagnostic_text_zh(signal_diagnosis.recommended_next_step)}",
        ]
        diagnosis_zh_path.write_text("\n".join(diagnosis_zh), encoding="utf-8")
        final_state["diagnosis_path"] = str(diagnosis_path)
        final_state["diagnosis_zh_path"] = str(diagnosis_zh_path)

    if "db_path" in config:
        store = RunStore(config["db_path"])
        store.init_db()
        now = datetime.now(UTC).isoformat()
        run_id = state.get("run_id", "run_manual")
        node_events = [
            ("Issue Reader", "success" if state.get("raw_issues") is not None else "skipped", len(state.get("raw_issues", [])), len(state.get("valid_issues", [])), False),
            ("Signal Scorer", "success" if state.get("scored_issues") is not None else "skipped", len(state.get("valid_issues", [])), len(state.get("scored_issues", [])), False),
            ("Pain Extractor", "success" if state.get("pain_points") is not None else "skipped", len(state.get("scored_issues", [])), len(state.get("pain_points", [])), True),
            ("Pain Clusterer", "success" if state.get("pain_clusters") is not None else "skipped", len(state.get("pain_points", [])), len(state.get("pain_clusters", [])), True),
            ("Opportunity Generator", "success" if state.get("opportunity_cards") is not None else "skipped", len(state.get("pain_clusters", [])), len(state.get("opportunity_cards", [])), True),
            ("Validator", "success" if state.get("valid_cards") is not None else "skipped", len(state.get("opportunity_cards", [])), len(state.get("valid_cards", [])), False),
            ("Reporter", "success", len(cards), len(cards), False),
        ]
        for idx, (node_name, event_status, input_count, output_count, llm_used) in enumerate(node_events, start=1):
            store.record_event(
                RunEvent(
                    event_id=f"{run_id}_event_{idx:02d}",
                    run_id=run_id,
                    node_name=node_name,
                    status=event_status,
                    started_at=now,
                    finished_at=now,
                    input_count=input_count,
                    output_count=output_count,
                    llm_used=llm_used,
                    message=f"{node_name} {event_status}",
                )
            )
        for idx, record in enumerate(state.get("quality_records", []), start=1):
            store.record_quality_record(
                run_id=run_id,
                quality_id=f"{run_id}_quality_{idx:02d}",
                record=record,
                created_at=now,
            )
        store.record_run(
            RunSummary(
                run_id=run_id,
                input_file=state.get("input_file", ""),
                started_at=config.get("started_at", now),
                finished_at=now,
                status=final_status,
                llm_enabled=config.get("mode") == "real",
                llm_model=config.get("llm_model"),
                llm_calls=final_state.get("llm_calls", 0),
                estimated_tokens=state.get("estimated_tokens", 0),
                total_issues=len(state.get("raw_issues", [])),
                valid_issues=len(state.get("valid_issues", [])),
                invalid_issues=len(state.get("invalid_issues", [])),
                cards_generated=len(state.get("opportunity_cards", [])),
                cards_valid=len(state.get("valid_cards", cards)),
                output_cards_path=str(output_cards_path),
                report_path=str(report_path),
                failure_reason=state.get("failure_reason"),
                config_snapshot=_safe_config_snapshot(config),
            )
        )

    final_state["status"] = final_status
    return final_state
