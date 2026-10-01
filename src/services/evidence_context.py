from src.schemas import EvidenceReference


HISTORICAL_CAVEAT = (
    "Closed issues are historical evidence, not proof of a current unresolved need. "
    "Verify closure reasons, subsequent fixes and present-day user impact."
)


def issue_references(issues):
    return {issue.url: EvidenceReference(**issue.model_dump()) for issue in issues}


def attach_cluster_evidence(clusters, pain_points):
    references = {ref.url: ref for point in pain_points for ref in point.evidence_context}
    for cluster in clusters:
        cluster.evidence_context = [references[url] for url in dict.fromkeys(cluster.evidence_urls) if url in references]
    return clusters
