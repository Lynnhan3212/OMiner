# Review and result handling

## Automatic mode (default for new runs)

Read `execution_result.json` first. It includes a final status, the underlying program status, stop stage/reason, scope, assumptions, counts, and `finished: true`. A null count means that stage did not yield a measurement; it is not zero. The report discloses that automated choices are not human reviewed. Review the preserved candidate list after execution when evaluating quality, including rejected sources.

Do not edit approval files or ask for approval during automatic execution. Automatic intake/plan decisions use `decided_by: automatic`, and source decisions use `confirmed_by: automatic`. These fields never count as human evaluation labels. A partial result is terminal. A fresh run is needed to retry; old artifacts must remain intact.

The following approval instructions apply only to explicit review mode and legacy manifests.

## Intake review

Read `outputs/runs/<run-id>/query_intake_review.json`. Present `agent_understanding`, important assumptions, and the effective boundary. For v1.6, `scope_diagnosis` is advisory, so a broad historical classification is not itself a reason to demand a long rewritten query.

After approval of the proposed boundary, preserve all existing fields and edit with a JSON-aware operation:

- Set `approval.approved` to boolean `true`. `status: approved` alone is insufficient for v1.6.
- Keep or append user-provided `important_keywords` / `exclude_keywords` without discarding previous edits.
- Record the approval context in `approval.notes` without claiming an automated decision was manual.
- Leave query identity, defaults, and generated understanding intact unless the user corrected them. The runner synchronizes status on valid resume.
- If `agent_generation.generation_method` is `unresolved`, require at least one real domain keyword in `important_keywords` before resuming. Do not invent it or preemptively claim recovery succeeded.

Use the project `QueryIntakeReview` schema to validate edits when practical. Keep the original input in the invocation manifest; keyword changes belong in the review, not in a changed `--query`. After a valid approved intake, the search plan is normally generated internally; do not introduce another approval for the compiled queries.

## Source review

Read `github_evidence_sources.json`, `github_evidence_source_review.json`, and, when needed, `github_search_trace.json` or `github_discovery_diagnosis.json`. Present a short recommendation grounded in domain fit, repository type, viability metadata, actual issue evidence, and warnings.

If the user approves specific sources, preserve identity fields (`discovery_id`, `query_id`, `query_fingerprint`, `search_plan_id`) and unrelated review edits. Set:

```json
{
  "status": "approved",
  "approved_sources": [
    {"repo": "owner/repo", "reason": "User approved this evidence source after review."}
  ],
  "confirmed_by": "human"
}
```

This is a fragment, not a replacement template. Update only approved entries; do not keep the same repository in `rejected_sources`. Correct contradictory old rejection reasons only for decisions actually changed by the user. Preserve scoring fields when moving existing entries, but validate their fields against `ApprovedGitHubSource`; discovery and review schemas are not necessarily identical. The final review must pass `GitHubEvidenceSourceReview` validation.

An empty `approved_sources` list cannot resume evidence collection. Never fabricate a source or approve everything to bypass the gate. Low viability is not proof of irrelevance, and a popular repository is not proof of strong pain evidence. Explicit auto-approval still follows the runner's policy.

## Results

Helper `skill_execution.json` records the latest attempt, separately from the runner's artifacts. `skill_invocation.json` records project, query, mode, and approval settings, without credentials. Neither replaces the underlying reports or proof.

Inspect the latest printed artifact paths and the report status. For a successful run, read `opportunity_cards.json` and the report. Verify card evidence URLs against the generated input file referenced by the report. Separate:

- selected repositories from repositories actually present in the final issue dataset;
- issue comment/reaction metadata totals from saved comment bodies;
- program signal scores from validated user demand;
- product hypotheses from observed issue descriptions;
- historic issue state from current state, unless current state was independently checked.

Use the user's language for the summary, while retaining original links and run identity. State the real or mock mode. Present the opportunity, affected users, supporting evidence, proposed next validation, and primary uncertainty. Usually 1-3 cards are sufficient, following the actual output.

`partial` can mean waiting for approval, no usable sources, or low signal after analysis. Use `next_action`, report and diagnosis to distinguish these. Do not describe a zero-match search as evidence that no market demand exists. Do not promote old card files when the latest attempt stopped earlier. Failure and unknown status must remain visible.

## Explicit regeneration or legacy continuation

The helper intentionally has no refresh flags and does not adopt unmanaged runs. If the user explicitly requests refresh of an existing run, preserve the run artifacts first and use the original known CLI options with `--refresh-query` or `--refresh-discovery` as appropriate. A query refresh can invalidate source review identity too; do not approve the old review for a changed query. New run IDs are simpler for a new direction.

Check `python -m src.runner --help` for the current checkout rather than guessing unsupported switches. Do not lower signal thresholds, force `--run-mode generate`, or erase reviews just to get cards.
