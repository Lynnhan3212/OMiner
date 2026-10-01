window.RESEARCH_SNAPSHOT = {
  "note": {
    "runId": "my_real_note_test",
    "originalQuery": "Find plugin or AI-agent opportunities for students using note-taking apps similar to GoodNotes, focusing on lecture notes, note organization, search, review, and cross-device workflows",
    "status": "success",
    "collectedAt": "2026-09-01",
    "issues": 50,
    "cards": [
      {
        "card_id": "opp_001",
        "title": "Conflict-safe graph sync and recovery",
        "target_user": "Users syncing Logseq graphs across multiple devices and cloud providers",
        "pain": "Sync can overwrite newer edits with older copies, create unnecessary backup files, and leave users uncertain whether their latest work is safe.",
        "source_issue_ids": [
          5901,
          3370,
          12140
        ],
        "evidence_urls": [
          "https://github.com/logseq/logseq/issues/5901",
          "https://github.com/logseq/logseq/issues/3370",
          "https://github.com/logseq/logseq/issues/12140"
        ],
        "frequency_signal": "Three related high-severity issues across iOS, macOS, Linux, Android, and iCloud/File Sync; frequency is directionally meaningful but still based on a small issue sample.",
        "current_workaround": "Close Logseq on other devices, retry or reinstall sync, manually clean generated files, and recover from backups or historical versions.",
        "mvp_idea": "A sync safety layer that snapshots files before sync, detects conflicting edits, shows a human-readable diff, and provides one-click restore or fork-before-overwrite.",
        "build_difficulty": "high",
        "monetization_hypothesis": "Freemium safety features with paid encrypted version history, extended retention, and multi-device conflict recovery.",
        "validation_plan": "Interview 10-15 users who experienced sync loss; prototype a conflict timeline and restore flow; test whether users would connect a graph and pay for protected history; measure successful recovery in a local simulator using generated concurrent edits.",
        "risk": "Deep integration with Logseq file formats and sync providers may be technically difficult, and users may distrust a third party with sensitive notes.",
        "assumptions": [
          "Sync-related data loss is frequent enough to motivate proactive protection.",
          "Users prefer guided conflict resolution over manual backup recovery.",
          "A tool can safely observe or wrap graph file operations without corrupting the graph."
        ],
        "confidence": "medium",
        "decision": "validate"
      },
      {
        "card_id": "opp_002",
        "title": "Large-graph performance diagnostics and safe mode",
        "target_user": "Users with large graphs, very large pages, or many enabled plugins",
        "pain": "Loading, re-indexing, typing, scrolling, and basic editing can become extremely slow or crash as graph and page size increase.",
        "source_issue_ids": [
          10283,
          10378,
          6154,
          8137,
          12078,
          8536
        ],
        "evidence_urls": [
          "https://github.com/logseq/logseq/issues/10283",
          "https://github.com/logseq/logseq/issues/10378",
          "https://github.com/logseq/logseq/issues/6154",
          "https://github.com/logseq/logseq/issues/8137",
          "https://github.com/logseq/logseq/issues/12078",
          "https://github.com/logseq/logseq/issues/8536"
        ],
        "frequency_signal": "Six high- or medium-severity issues spanning Android, Windows, macOS, and general editing; strong cross-platform signal, though issue counts do not establish user prevalence.",
        "current_workaround": "Split large pages, disable plugins, wait between actions, force-quit, downgrade, or retry indexing with developer tools open.",
        "mvp_idea": "A diagnostic companion that profiles graph load, indexing, plugins, and page size, then offers safe mode, plugin isolation, large-page detection, and actionable cleanup recommendations.",
        "build_difficulty": "high",
        "monetization_hypothesis": "Paid performance diagnostics for power users and teams, or a plugin-quality monitoring product for the Logseq ecosystem.",
        "validation_plan": "Recruit users with graphs above defined size thresholds; collect anonymized startup and interaction traces; test a browser-based prototype of the diagnostic report; validate whether recommended actions resolve lag without data loss.",
        "risk": "An external tool may not be able to access the renderer or plugin runtime deeply enough to diagnose root causes; users may expect fixes rather than reports.",
        "assumptions": [
          "A meaningful share of performance problems can be attributed to identifiable pages, plugins, or indexing tasks.",
          "Users will run diagnostics on private graph data if processing is local.",
          "Safe-mode and profiling capabilities can be delivered without modifying source files."
        ],
        "confidence": "medium",
        "decision": "validate"
      },
      {
        "card_id": "opp_003",
        "title": "Android graph access with least-privilege storage",
        "target_user": "Android users with large or externally synchronized graphs, especially privacy-conscious users",
        "pain": "The Android app may crash while loading large graphs and requests unrestricted access to device files, while some storage providers such as Nextcloud cannot be selected reliably.",
        "source_issue_ids": [
          10283,
          7476,
          9403
        ],
        "evidence_urls": [
          "https://github.com/logseq/logseq/issues/10283",
          "https://github.com/logseq/logseq/issues/7476",
          "https://github.com/logseq/logseq/issues/9403"
        ],
        "frequency_signal": "Three high-severity Android issues covering graph loading, filesystem permissions, and provider access; meaningful thematic signal but limited evidence of scale.",
        "current_workaround": "Downgrade or use a smaller graph, grant broad filesystem permission, or switch away from Nextcloud and other document providers.",
        "mvp_idea": "A privacy-first Android graph bridge using scoped storage and provider-aware access, with local graph indexing, incremental loading, crash-safe startup, and an explicit permission audit.",
        "build_difficulty": "high",
        "monetization_hypothesis": "Paid Android companion or subscription for encrypted mobile sync, provider connectors, and reliable large-graph access.",
        "validation_plan": "Interview Android users using Nextcloud or large graphs; build a narrow prototype that opens a graph through the Storage Access Framework with read/write scopes; benchmark startup and memory use; test willingness to pay for reliable mobile access without unrestricted permissions.",
        "risk": "Android filesystem and provider APIs vary substantially, and reproducing Logseq compatibility without official integration may be impractical.",
        "assumptions": [
          "Users value least-privilege permissions enough to change apps or pay.",
          "Incremental loading can materially reduce large-graph crashes.",
          "A companion can integrate with Logseq's Markdown graph format without relying on private APIs."
        ],
        "confidence": "low",
        "decision": "watch"
      }
    ],
    "commentMetadataCount": 1084,
    "reactionMetadataCount": 425,
    "savedCommentCount": 150,
    "highSignalCount": 37,
    "approvedRepos": [
      "logseq/logseq",
      "laurent22/joplin"
    ],
    "collectedRepos": [
      "logseq/logseq"
    ],
    "confirmedBy": "human",
    "evidence": [
      {
        "id": 12078,
        "title": "slow/lagging cursor #11223",
        "url": "https://github.com/logseq/logseq/issues/12078",
        "state": "open",
        "comments_count": 52,
        "reactions_count": 0
      },
      {
        "id": 9403,
        "title": "Android: cannot select Nextcloud-hosted directory",
        "url": "https://github.com/logseq/logseq/issues/9403",
        "state": "open",
        "comments_count": 47,
        "reactions_count": 36
      },
      {
        "id": 6154,
        "title": "Crash when trying to re-index, possibly due to large graph",
        "url": "https://github.com/logseq/logseq/issues/6154",
        "state": "open",
        "comments_count": 35,
        "reactions_count": 0
      },
      {
        "id": 7476,
        "title": "Android permissions is too permissive \"All Files Read/Write/Delete Access\"",
        "url": "https://github.com/logseq/logseq/issues/7476",
        "state": "open",
        "comments_count": 28,
        "reactions_count": 14
      },
      {
        "id": 8536,
        "title": "Unable to close Logseq, stuck at Syncing internal status",
        "url": "https://github.com/logseq/logseq/issues/8536",
        "state": "open",
        "comments_count": 26,
        "reactions_count": 3
      },
      {
        "id": 10283,
        "title": "app crashes after loading graph",
        "url": "https://github.com/logseq/logseq/issues/10283",
        "state": "open",
        "comments_count": 20,
        "reactions_count": 0
      },
      {
        "id": 8137,
        "title": "Performance issues when editing big (massive) pages",
        "url": "https://github.com/logseq/logseq/issues/8137",
        "state": "open",
        "comments_count": 20,
        "reactions_count": 3
      },
      {
        "id": 10378,
        "title": "Performance lags, actions slow",
        "url": "https://github.com/logseq/logseq/issues/10378",
        "state": "open",
        "comments_count": 18,
        "reactions_count": 4
      },
      {
        "id": 5901,
        "title": "Data loss on iOS",
        "url": "https://github.com/logseq/logseq/issues/5901",
        "state": "open",
        "comments_count": 17,
        "reactions_count": 0
      },
      {
        "id": 12140,
        "title": "File sync storage exceeds limit",
        "url": "https://github.com/logseq/logseq/issues/12140",
        "state": "open",
        "comments_count": 14,
        "reactions_count": 0
      },
      {
        "id": 3370,
        "title": "write most file in bak folder",
        "url": "https://github.com/logseq/logseq/issues/3370",
        "state": "open",
        "comments_count": 14,
        "reactions_count": 0
      }
    ],
    "sourceReview": {
      "discovery_id": "github_discovery_001",
      "status": "approved",
      "approved_sources": [
        {
          "repo": "logseq/logseq",
          "reason": "Auto-rejected because evidence_quality=strong and repo_relevance_score=0.0."
        },
        {
          "repo": "laurent22/joplin",
          "reason": "Auto-rejected because evidence_quality=medium and repo_relevance_score=0.0."
        }
      ],
      "rejected_sources": [],
      "confirmed_by": "human",
      "notes": "Auto-approval found candidates but no source met the approval threshold; review sources manually."
    }
  },
  "partial": {
    "runId": "v18_customer_service_acceptance_01",
    "candidateCount": 0,
    "attempts": [
      {
        "stage": "repository",
        "query": "\"customer support\" \"contact center\"",
        "status": "success",
        "result_count": 16,
        "error": null,
        "used_term_ids": [
          "term_domain_seed_001",
          "term_repo_term_007"
        ]
      },
      {
        "stage": "repository",
        "query": "\"support agent\" \"help desk\"",
        "status": "success",
        "result_count": 32,
        "error": null,
        "used_term_ids": [
          "term_domain_seed_002",
          "term_repo_term_008"
        ]
      },
      {
        "stage": "repository",
        "query": "\"human handoff\" \"customer service\"",
        "status": "success",
        "result_count": 19,
        "error": null,
        "used_term_ids": [
          "term_domain_seed_003",
          "term_repo_term_009"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system missing feature is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_017"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system workflow blocker is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_018"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system manual workaround is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_019"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system human handoff is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_021"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system agent handoff is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_022"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:zhangwenhao66/awesome-customer-support-software missing feature is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_017"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:zhangwenhao66/awesome-customer-support-software workflow blocker is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_018"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:zhangwenhao66/awesome-customer-support-software manual workaround is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_019"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:zhangwenhao66/awesome-customer-support-software human handoff is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_021"
        ]
      },
      {
        "stage": "repo_scoped_issue",
        "query": "repo:zhangwenhao66/awesome-customer-support-software agent handoff is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_022"
        ]
      },
      {
        "stage": "global_issue_safety_net",
        "query": "\"customer support\" \"missing feature\" is:issue in:title,body,comments -\"general chatbot marketing\" -\"sales automation\" -\"personal productivity assistants\"",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_domain_seed_001",
          "term_issue_problem_term_017"
        ]
      },
      {
        "stage": "global_issue_safety_net",
        "query": "\"support agent\" \"workflow blocker\" is:issue in:title,body,comments -\"general chatbot marketing\" -\"sales automation\" -\"personal productivity assistants\"",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_domain_seed_002",
          "term_issue_problem_term_018"
        ]
      },
      {
        "stage": "global_issue_safety_net",
        "query": "\"human handoff\" \"feature request\" is:issue in:title,body,comments -\"general chatbot marketing\" -\"sales automation\" -\"personal productivity assistants\"",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_domain_seed_003"
        ]
      },
      {
        "stage": "expansion",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system missing feature is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_017"
        ]
      },
      {
        "stage": "expansion",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system workflow blocker is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_018"
        ]
      },
      {
        "stage": "expansion",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system manual workaround is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_019"
        ]
      },
      {
        "stage": "expansion",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system integration problem is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_020"
        ]
      },
      {
        "stage": "expansion",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system human handoff is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_021"
        ]
      },
      {
        "stage": "expansion",
        "query": "repo:Isaac24Karat/ai-booking-optimization-system agent handoff is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_022"
        ]
      },
      {
        "stage": "expansion",
        "query": "repo:zhangwenhao66/awesome-customer-support-software missing feature is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_017"
        ]
      },
      {
        "stage": "expansion",
        "query": "repo:zhangwenhao66/awesome-customer-support-software workflow blocker is:issue in:title,body,comments",
        "status": "success",
        "result_count": 0,
        "error": null,
        "used_term_ids": [
          "term_issue_problem_term_018"
        ]
      }
    ],
    "originalCauses": [
      "Search terms may be too narrow, too product-name-specific, or mismatched with GitHub issue language.",
      "The target domain may use adjacent keywords that were not included in the approved search plan.",
      "Repository search may not have found enough relevant repos to anchor issue discovery."
    ],
    "originalActions": [
      "Review query_search_plan.json and add broader workflow or pain terms before rerunning.",
      "Add repo_scope hints when you already know representative repositories for this domain.",
      "Use fallback_issue_queries to test adjacent GitHub vocabulary before treating the domain as low-signal."
    ]
  }
};
