# Amp lane fixtures

- `stream-ok.jsonl`, `stream-error.jsonl`, `stream-cut.jsonl`: synthetic `amp -x --stream-json` output. They follow
  the event types the installed Amp documents (Claude Code's stream-json shape: `system` init, `assistant` with
  `message.usage`, `user` tool results, and a final `result` carrying `duration_ms`, `num_turns`, `session_id`,
  `usage` and `permission_denials`). No live `amp -x` run has been captured, so re-check them against the first real
  run and replace them with a sanitised capture.
- `threads-usage.txt`: a sanitised copy of `plans/amp-codex/probe/thread-usage-details.txt` (`amp threads usage
  <thread> --details` on an archived thread, amp 0.0.1794528069). Its `Cost:` line is what the lane reads.
