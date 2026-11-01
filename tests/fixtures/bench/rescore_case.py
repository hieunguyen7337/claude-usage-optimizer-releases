"""Small Suite R adjudication case shared by lane-bench rescore tests."""

ITEM_DEFECTS = {
    "001": [
        {"id": "D1", "file": "src/a.py", "line": 10, "line_end": 10},
        {"id": "D2", "file": "src/a.py", "line": 40, "line_end": 40},
    ],
    "002": [],
}

FINDINGS = [
    {"fid": "luna-low:001:0", "arm": "luna-low", "lane": "luna", "effort": "low", "rep": 1,
     "item": "001", "kind": "planted", "finding_index": 0, "file": "src/a.py", "line": 10,
     "severity": "high", "description": "planted match", "matched_defect": "001:D1", "strict": True},
    {"fid": "luna-low:001:1", "arm": "luna-low", "lane": "luna", "effort": "low", "rep": 1,
     "item": "001", "kind": "planted", "finding_index": 1, "file": "src/a.py", "line": 55,
     "severity": "medium", "description": "near miss assigned to D2", "matched_defect": None, "strict": True},
    {"fid": "luna-low:001:2", "arm": "luna-low", "lane": "luna", "effort": "low", "rep": 1,
     "item": "001", "kind": "planted", "finding_index": 2, "file": "src/a.py", "line": 80,
     "severity": "low", "description": "first real issue report", "matched_defect": None, "strict": True},
    {"fid": "luna-low:001:3", "arm": "luna-low", "lane": "luna", "effort": "low", "rep": 1, "item": "001", "kind": "planted", "finding_index": 3, "file": "src/a.py", "line": 81,
     "severity": "low", "description": "duplicate real issue report", "matched_defect": None, "strict": True},
    {"fid": "luna-low:001:4", "arm": "luna-low", "lane": "luna", "effort": "low", "rep": 1, "item": "001", "finding_index": 4, "file": "src/a.py", "line": 40,
     "severity": "medium", "description": "old location match adjudicated as other issue",
     "matched_defect": "001:D2", "strict": True},
    {"fid": "luna-low:001:5", "arm": "luna-low", "lane": "luna", "effort": "low", "rep": 1,
     "item": "001", "kind": "planted", "finding_index": 5, "file": "src/a.py", "line": 70,
     "severity": "low", "description": "false alarm", "matched_defect": None, "strict": True},
]

ASSIGNMENTS = [
    {"fid": "luna-low:001:1", "issue_id": "001:D2"},
    {"fid": "luna-low:001:2", "issue_id": "001:U1"},
    {"fid": "luna-low:001:3", "issue_id": "001:U1"},
    {"fid": "luna-low:001:4", "issue_id": "001:U2"},
    {"fid": "luna-low:001:5", "issue_id": "001:U3"},
]

ISSUES = [
    {"issue_id": "001:U1", "item": "001", "file": "src/a.py", "line": 80, "line_end": 81,
     "final_verdict": "real", "scope": "in_diff", "severity_judged": "medium"},
    {"issue_id": "001:U2", "item": "001", "file": "src/a.py", "line": 40, "line_end": 40,
     "final_verdict": "real", "scope": "out_of_diff", "severity_judged": "high"},
    {"issue_id": "001:U3", "item": "001", "file": "src/a.py", "line": 70, "line_end": 70,
     "final_verdict": "speculative", "scope": "in_diff", "severity_judged": "low"},
]

MATCHED_AUDIT = [
    {"fid": "luna-low:001:0", "matched_defect": "001:D1", "label": "describes"},
    {"fid": "luna-low:001:4", "matched_defect": "001:D2", "label": "other_issue"},
]

OUTCOME_HEADER = {
    "type": "header", "schema_version": 1, "suite": "rescore-test", "class": "review", "window": 5,
    "item_count": 2, "total_defects": 2, "planted_items": ["001"], "control_items": ["002"],
    "item_defect_ids": {"001": ["D1", "D2"], "002": []}, "arms": ["luna-low"],
}

OUTCOMES = [
    {"type": "outcome", "arm": "luna-low", "lane": "luna", "model": "fixture-model", "effort": "low",
     "rep": 1, "provider": "codex", "item": "001", "kind": "planted", "status": "complete",
     "run_present": True, "skipped": False, "infra_failure": False, "findings_present": True,
     "lane_exit": "0", "cost": 1.0, "cost_unit": "credits", "pct_week": 0.1, "tokens": 100},
    {"type": "outcome", "arm": "luna-low", "lane": "luna", "model": "fixture-model", "effort": "low",
     "rep": 1, "provider": "codex", "item": "002", "kind": "control", "status": "complete",
     "run_present": True, "skipped": False, "infra_failure": False, "findings_present": True,
     "lane_exit": "0", "cost": 1.0, "cost_unit": "credits", "pct_week": 0.1, "tokens": 100},
]
