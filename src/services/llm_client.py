import json
from typing import Any

from openai import OpenAI

from src.schemas import OpportunityCard, PainCluster, PainPoint, ScoredIssue


CHINESE_CARD_FIELDS = [
    "title",
    "target_user",
    "pain",
    "frequency_signal",
    "current_workaround",
    "mvp_idea",
    "monetization_hypothesis",
    "validation_plan",
    "risk",
    "assumptions",
]


MOCK_CHINESE_TRANSLATIONS = {
    "Export reliability tool": "导出可靠性工具",
    "Large-export reliability assistant": "大文件导出可靠性助手",
    "Teams using exports in production": "在生产环境中依赖导出功能的团队",
    "Teams using export features in production reporting workflows": "在生产报表流程中使用导出功能的团队",
    "Teams relying on exports for production reporting": "依赖导出功能完成生产报表的团队",
    "Large export jobs fail and block reporting workflows.": "大文件导出任务失败，并阻塞报表工作流。",
    "Users repeatedly report unreliable large export workflows and manual retry workarounds.": "用户反复反馈大文件导出流程不稳定，只能依靠人工重试等临时办法。",
    "Two issues and several comments mention export failures.": "两个 Issue 和多条评论都提到了导出失败。",
    "5 related pain points mention export reliability.": "5 个相关痛点都提到了导出可靠性问题。",
    "Users retry manually.": "用户只能手动重试。",
    "Manual retries, splitting files, or waiting for maintainers.": "用户只能手动重试、拆分文件，或等待维护者修复。",
    "A retry and monitoring wrapper for export jobs.": "导出任务的重试和监控封装工具。",
    "A lightweight export retry, monitoring, and notification wrapper for large report jobs.": "一个轻量级的大报表导出重试、监控和通知工具。",
    "Teams may pay for reliable reporting automation.": "如果报表流程经常依赖导出，团队可能愿意为可靠性自动化付费。",
    "Teams with recurring reporting workflows may pay for reliability automation.": "有周期性报表流程的团队，可能愿意为导出可靠性自动化付费。",
    "Contact issue authors and test a prototype.": "联系 Issue 作者，测试一个最小原型是否能解决他们的流程问题。",
    "Contact issue authors and test whether a retry and monitoring prototype solves their workflow.": "联系 Issue 作者，验证重试和监控原型是否能解决他们的实际流程。",
    "The upstream project may fix export reliability.": "上游项目可能直接修复导出可靠性问题。",
    "The upstream project may fix this natively, reducing the value of a standalone tool.": "上游项目可能原生修复这个问题，从而降低独立工具的价值。",
    "Reporting workflows are important enough to validate.": "报表工作流足够重要，值得进一步验证。",
    "Recurring reporting workflows are important enough to justify a separate tool.": "周期性报表工作流足够重要，可能支撑一个独立工具。",
}


def get_llm_client(config: dict[str, Any]):
    if config.get("mode") == "real":
        return OpenAICompatibleLLMClient(
            api_key=config["llm_api_key"],
            model=config["llm_model"],
            base_url=config.get("llm_base_url"),
        )
    return MockLLMClient()


class MockLLMClient:
    def parse_query_intake(self, query: str, schema: dict[str, Any]) -> dict[str, Any]:
        text = query.lower()
        if "note" in text or "goodnotes" in text:
            constraints = []
            if "lecture" in text:
                constraints.append("lecture notes")
            if "search" in text:
                constraints.append("search")
            if "review" in text:
                constraints.append("review")
            if "sync" in text or "cross-device" in text:
                constraints.append("cross-device workflows")
            related_terms = ["pdf annotation", "handwriting", "OCR", "sync"] if "goodnotes" in text else []
            return {
                "target_domain": "note-taking software",
                "target_user": "students" if "student" in text else "",
                "opportunity_type": "plugin or AI-agent opportunities",
                "constraints": constraints,
                "must_include_terms": ["note taking", "notes app"],
                "related_terms": related_terms,
                "exclude_terms": ["course notes", "tutorial", "homework"],
                "assumptions": ["Search adjacent open-source note-taking workflows for GitHub issue evidence."],
                "confidence": 0.78,
                "risk_notes": ["GoodNotes may not expose GitHub issue evidence directly."],
            }
        return {}

    def decompose_query(self, query_spec) -> dict[str, Any]:
        text = query_spec.original_query.lower()
        if "note" in text or "goodnotes" in text:
            return {
                "normalized_goal": "Find plugin or AI-agent opportunities for student note-taking workflows.",
                "intent": "market",
                "target_domain": query_spec.target_domain,
                "target_user": query_spec.target_user,
                "opportunity_type": query_spec.opportunity_type,
                "domain_terms": ["note taking", "notes app", "digital notebook"],
                "workflow_terms": ["lecture notes", "note organization", "search", "review", "cross-device sync"],
                "product_terms": ["pdf annotation", "handwriting notes", "OCR", "spaced repetition"],
                "pain_terms": ["sync conflict", "search not working", "missing OCR", "export problem"],
                "synonyms": ["markdown notes", "study notes", "knowledge base"],
                "repo_hints": [],
                "negative_terms": query_spec.excluded_keywords,
                "confidence": 0.78,
                "needs_human_review": True,
                "risk_notes": [
                    "GoodNotes itself may not provide open GitHub issue evidence; search adjacent note-taking workflows."
                ],
            }
        return {}

    def translate_opportunity_card_to_chinese(self, card: OpportunityCard) -> dict[str, Any]:
        return _translate_card_with_mock_dictionary(card)

    def extract_pain_points(self, scored_issues: list[ScoredIssue]) -> list[PainPoint]:
        points: list[PainPoint] = []
        for idx, scored in enumerate(scored_issues[:5], start=1):
            issue = scored.issue
            points.append(
                PainPoint(
                    pain_id=f"pain_{idx:03d}",
                    source_issue_id=issue.id,
                    evidence_url=issue.url,
                    target_user="Teams relying on exports for production reporting",
                    pain="Export workflows are unreliable for larger reporting jobs.",
                    scenario="A team needs to export a large report and the workflow fails or requires manual retries.",
                    current_workaround="Users retry manually or split export jobs.",
                    severity="medium" if scored.score < 5 else "high",
                )
            )
        return points

    def cluster_pain_points(self, pain_points: list[PainPoint]) -> list[PainCluster]:
        if not pain_points:
            return []
        return [
            PainCluster(
                cluster_id="cluster_001",
                title="Reliable large-export workflow",
                source_issue_ids=[point.source_issue_id for point in pain_points],
                evidence_urls=[point.evidence_url for point in pain_points],
                pain_summary="Users repeatedly report unreliable large export workflows and manual retry workarounds.",
                target_user="Teams using export features in production reporting workflows",
                current_workaround="Manual retries, splitting files, or waiting for maintainers.",
                signal_summary=f"{len(pain_points)} related pain points mention export reliability.",
            )
        ]

    def generate_opportunity_cards(self, pain_clusters: list[PainCluster], max_cards: int) -> list[OpportunityCard]:
        cards: list[OpportunityCard] = []
        for idx, cluster in enumerate(pain_clusters[:max_cards], start=1):
            cards.append(
                OpportunityCard(
                    card_id=f"card_{idx:03d}",
                    title="Large-export reliability assistant",
                    target_user=cluster.target_user,
                    pain=cluster.pain_summary,
                    source_issue_ids=cluster.source_issue_ids,
                    evidence_urls=cluster.evidence_urls,
                    frequency_signal=cluster.signal_summary,
                    current_workaround=cluster.current_workaround,
                    mvp_idea="A lightweight export retry, monitoring, and notification wrapper for large report jobs.",
                    build_difficulty="medium",
                    monetization_hypothesis="Teams with recurring reporting workflows may pay for reliability automation.",
                    validation_plan="Contact issue authors and test whether a retry and monitoring prototype solves their workflow.",
                    risk="The upstream project may fix this natively, reducing the value of a standalone tool.",
                    assumptions=["Recurring reporting workflows are important enough to justify a separate tool."],
                    confidence="medium",
                    decision="validate",
                )
            )
        return cards


class OpenAICompatibleLLMClient:
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 2, "timeout": 60.0}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def _json_chat(self, system: str, payload: dict[str, Any]) -> Any:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def parse_query_intake(self, query: str, schema: dict[str, Any]) -> dict[str, Any]:
        result = self._json_chat(
            (
                "You parse product/opportunity search requests for a GitHub evidence mining agent. "
                "Return only JSON matching the supplied schema. Do not search GitHub, do not invent evidence, "
                "and do not claim willingness to pay. Use concise product language. "
                "Prefer search boundary terms that are likely to appear in GitHub issues, repository names, "
                "descriptions, or topics."
            ),
            {"user_query": query, "schema": schema},
        )
        return result if isinstance(result, dict) else {}

    def translate_opportunity_card_to_chinese(self, card: OpportunityCard) -> dict[str, Any]:
        result = self._json_chat(
            (
                "Translate an opportunity card into natural Chinese product language. "
                "Return only JSON with key card_zh. Do not add new evidence, new claims, or stronger conclusions. "
                "Only translate or lightly rephrase the supplied fields. card_zh must contain: title, target_user, "
                "pain, frequency_signal, current_workaround, mvp_idea, monetization_hypothesis, validation_plan, "
                "risk, assumptions. assumptions must be a list of strings."
            ),
            {"opportunity_card": card.model_dump()},
        )
        translated = result.get("card_zh", {})
        if not isinstance(translated, dict):
            translated = {}
        return _normalize_translated_card(card, translated)

    def decompose_query(self, query_spec) -> dict[str, Any]:
        return self._json_chat(
            (
                "You are a query decomposition assistant for a GitHub opportunity-mining agent.\n\n"
                "Your job is to translate a user's product/opportunity query into structured search-planning vocabulary.\n\n"
                "You must not search GitHub.\n"
                "You must not invent evidence.\n"
                "You must not decide whether an opportunity is commercially validated.\n"
                "You must not output final GitHub search queries.\n"
                "You must only return valid JSON matching the schema.\n\n"
                "GitHub evidence can support pain signals, but it does not prove willingness to pay.\n"
                "Prefer terms that are likely to appear in GitHub issue titles, bodies, comments, repo names, descriptions, or topics."
            ),
            {
                "user_query": query_spec.original_query,
                "query_spec": query_spec.model_dump(),
                "schema": {
                    "normalized_goal": "string",
                    "intent": "topic | repo | org | technology | problem | market | unknown",
                    "target_domain": "string",
                    "target_user": "string",
                    "opportunity_type": "string",
                    "domain_terms": ["string"],
                    "workflow_terms": ["string"],
                    "product_terms": ["string"],
                    "pain_terms": ["string"],
                    "synonyms": ["string"],
                    "repo_hints": ["owner/repo"],
                    "negative_terms": ["string"],
                    "confidence": 0.0,
                    "needs_human_review": True,
                    "risk_notes": ["string"],
                },
                "rules": [
                    "Use short terms or compact phrases.",
                    "Do not copy the full user query as a search term.",
                    "Avoid generic terms unless paired with a concrete domain or workflow.",
                    "If the named product is likely not an open-source GitHub repo, add adjacent open-source ecosystem terms.",
                    "If uncertain, set confidence below 0.7 and explain in risk_notes.",
                    "For unknown focused domains, needs_human_review must be true.",
                ],
            },
        )

    def _normalize_pain_point(
        self,
        item: dict[str, Any],
        index: int,
        scored_issues: list[ScoredIssue],
    ) -> dict[str, Any]:
        issue_by_id = {str(scored.issue.id): scored.issue for scored in scored_issues}
        score_by_id = {str(scored.issue.id): scored.score for scored in scored_issues}
        source_ids = item.get("source_issue_ids") or item.get("issues") or []
        if not isinstance(source_ids, list):
            source_ids = [source_ids]
        source_issue_id = item.get("source_issue_id") or (source_ids[0] if source_ids else None)
        fallback_issue = scored_issues[0].issue if scored_issues else None
        issue = issue_by_id.get(str(source_issue_id)) or fallback_issue
        pain = item.get("pain") or item.get("pain_point") or item.get("pain_summary")
        if not pain and issue:
            pain = issue.title
        severity = item.get("severity")
        if severity not in {"low", "medium", "high"}:
            severity = "high" if source_issue_id and score_by_id.get(str(source_issue_id), 0) >= 5 else "medium"

        return {
            "pain_id": item.get("pain_id") or f"pain_{index:03d}",
            "source_issue_id": source_issue_id or (issue.id if issue else f"unknown_{index}"),
            "evidence_url": item.get("evidence_url") or (issue.url if issue else "unknown"),
            "target_user": item.get("target_user") or "Users affected by the linked GitHub issue",
            "pain": pain or "Unspecified pain point",
            "scenario": item.get("scenario") or (issue.title if issue else "The linked workflow does not behave as expected."),
            "current_workaround": item.get("current_workaround") or "unknown",
            "severity": severity,
        }

    def extract_pain_points(self, scored_issues: list[ScoredIssue]) -> list[PainPoint]:
        result = self._json_chat(
            (
                "Extract concrete pain points from GitHub issues. Return only JSON with key pain_points. "
                "Each item must contain: pain_id, source_issue_id, evidence_url, target_user, pain, "
                "scenario, current_workaround, severity. severity must be one of low, medium, high. "
                "Respect issue state, state_reason, closed_at and comments. Closed issues describe historical "
                "pain, not current unresolved needs. Open state also does not verify present-day demand. "
                "Do not infer an unresolved problem from an issue whose comments describe a fix."
            ),
            {"scored_issues": [item.model_dump() for item in scored_issues]},
        )
        return [
            PainPoint(**self._normalize_pain_point(item, index, scored_issues))
            for index, item in enumerate(result.get("pain_points", []), start=1)
        ]

    def cluster_pain_points(self, pain_points: list[PainPoint]) -> list[PainCluster]:
        result = self._json_chat(
            (
                "Cluster similar product pain points. Return only JSON with key pain_clusters. "
                "Each item must contain: cluster_id, title, source_issue_ids, evidence_urls, "
                "pain_summary, target_user, current_workaround, signal_summary. "
                "Respect evidence_context: closed issues are historical, current persistence unverified. "
                "Do not merge historical reports into claims of confirmed current unresolved demand."
            ),
            {"pain_points": [item.model_dump() for item in pain_points]},
        )
        return [PainCluster(**item) for item in result.get("pain_clusters", [])]

    def generate_opportunity_cards(self, pain_clusters: list[PainCluster], max_cards: int) -> list[OpportunityCard]:
        result = self._json_chat(
            (
                "Generate evidence-linked opportunity cards. Return only JSON with key opportunity_cards. "
                "Each item must contain: card_id, title, target_user, pain, source_issue_ids, evidence_urls, "
                "frequency_signal, current_workaround, mvp_idea, build_difficulty, monetization_hypothesis, "
                "validation_plan, risk, assumptions, confidence, decision. build_difficulty and confidence "
                "must be low, medium, or high. decision must be build, validate, watch, or reject. "
                "Use evidence_context issue states and closure information. Closed evidence supports only "
                "historical pain hypotheses, never a confirmed current unresolved need. If all evidence is "
                "closed, use low confidence and validate/watch/reject, not build. Explicitly qualify the pain "
                "as historical and require checking fixes and current users. Open status alone also does "
                "not prove current unmet demand. Cite only supplied evidence URLs."
            ),
            {"pain_clusters": [item.model_dump() for item in pain_clusters], "max_cards": max_cards},
        )
        return [OpportunityCard(**item) for item in result.get("opportunity_cards", [])]


def _translate_text_with_mock_dictionary(text: str) -> str:
    if text in MOCK_CHINESE_TRANSLATIONS:
        return MOCK_CHINESE_TRANSLATIONS[text]
    translated = text
    for source, target in sorted(MOCK_CHINESE_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True):
        translated = translated.replace(source, target)
    return translated


def _normalize_translated_card(card: OpportunityCard, translated: dict[str, Any]) -> dict[str, Any]:
    source = card.model_dump()
    normalized: dict[str, Any] = {}
    for field in CHINESE_CARD_FIELDS:
        value = translated.get(field)
        if field == "assumptions":
            if isinstance(value, list):
                normalized[field] = [str(item) for item in value]
            else:
                normalized[field] = source.get(field, [])
        elif isinstance(value, str) and value.strip():
            normalized[field] = value.strip()
        else:
            normalized[field] = source.get(field, "")
    return normalized


def _translate_card_with_mock_dictionary(card: OpportunityCard) -> dict[str, Any]:
    source = card.model_dump()
    translated: dict[str, Any] = {}
    for field in CHINESE_CARD_FIELDS:
        value = source[field]
        if isinstance(value, list):
            translated[field] = [_translate_text_with_mock_dictionary(str(item)) for item in value]
        else:
            translated[field] = _translate_text_with_mock_dictionary(str(value))
    return translated
