Review the code change in {{ITEM_PATH}}/diff.patch for real bugs. Post-change Python files under
{{ITEM_PATH}}/post/ give context. Report only actionable correctness defects.

Write findings.jsonl in the workspace root ({{ITEM_PATH}}), one JSON object per line:

{"file": "src/app.py", "line": 42, "severity": "high", "description": "Explain the bug and its effect."}

Severity must be high, medium or low. If there are no real defects, write an empty findings.jsonl file.
