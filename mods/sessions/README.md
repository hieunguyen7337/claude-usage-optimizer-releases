# Sessions

The Claude app's session list, inside the CLI: every local and cloud session, grouped by repository, and a session
view with its transcript, a composer and action keys. `/sessions`, or `.` alone in an empty prompt, opens the pane;
Esc goes back, and Esc at the list closes it.

## Keys

The list:

- a: show or hide inactive (archived) sessions
- r: refresh
- Pick a row to open its session view.

The session view. Each action key is drawn only when the session offers that action; a key with no hotkey is still
drawn as a button.

- s: send (the composer below the transcript)
- o: open in the Claude app
- c: copy the resume command
- b: branch diff
- r: refresh
- p: read the page of older events
- x: archive
- d: delete
- e: expand, or collapse, the transcript (see below)
- i, y, m: interrupt, approve the held message, set the permission mode. These open the Claude app; the pane does not
  act on them.

`e` is listed in the session view with or without a row. It is not bound anywhere else in the pane.

## What the list shows

- A summary line first: how many sessions are shown, then how many need you, are working, are ready for review, idle,
  offline or archived.
- Sessions grouped by repository. Rows that need you lead their group, and groups holding one lead the list; Other
  (no repository) stays last. Below 80 cells a group header drops the repository's owner.
- At 100 cells or more a row is one line. Narrower, it is the state mark, the unread mark and the title, wrapped to
  at most two rows, then a dim line of facts (state, where it runs, its role, branch, age, context and model with
  effort), wrapped too.
- A session shows once. A local session joins its Claude app row by title, or by repository and branch when only one
  app row matches both.
- Every kit mirror (from `~/.local/state/lanes/mains.json`) is listed and tagged `mirror`, even when it is archived or
  offline. A mirror the list API leaves out is read by its id; one that cannot be read becomes a row naming the
  reason, such as a session bound to the device that started it. A mirror whose session was deleted on claude.ai
  (HTTP 404) is left out of the list; opening a session that turns out deleted goes back to the list with a note.
- The footer gives the keys, wrapped at the pane's width, and a note when the read was cut short.

## What the session view shows

Nothing is cut at the pane's width: a longer header, note, text, tool head, result line or notice wraps onto more
rows, with wide characters counted as two cells.

- The header: title; repository, branch, head, dirty and unpushed; state, kind, model, permission mode, context.
- The transcript, oldest first. A prompt or assistant text is drawn at four wrapped rows, and the rows it does not show are
  marked "+N lines". The newest assistant text is the exception: it is drawn in full, so the latest answer can be read
  without expanding anything.
- A tool call is a head line: its name, its label (up to 400 characters) and its status, wrapped to at most two
  rows, all of them in the expanded view. A call with subagent lines is a button: opened, it
  shows them under its head.
- A tool result keeps its text: a string, or the text blocks of a content list; images are skipped. The text is cleaned
  as assistant text is (control, ANSI and bidi characters removed) and kept to 4000 characters per result. A result
  shows only in the expanded view.
- Folded (the default), the transcript shows its newest 300 lines.

## Expanded view (`e`)

`e` toggles the expanded view for the open session:

- every prompt and text is drawn in full;
- each tool call's result body is drawn under its head: up to 20 rows, then "+N lines";
- the transcript shows its newest 2000 lines rather than 300.

The view opens folded every time a session is opened, so the expansion is reset whenever another session is opened.

## Notes

- Tool result text is shown as the transcript's text is: cleaned of control and bidi characters. The mod does not
  redact credentials from it, and nothing in the mod does.
- On a surface with no composer (the mobile surface), the transcript and tool results are drawn as in the terminal
  pane. The action row, with `e`, is drawn there too.
- Cloud sessions are read from the Claude sessions API. A local session shows the text of `claude logs` for it instead of
  a transcript, so the transcript keys and `e` change nothing there.
- A session bound to the computer that started it answers the pane's own reads with HTTP 403 (claude.ai wants a
  trusted-device proof that only Claude Code's client sends). The view then shows its condensed log, read through
  Claude Code's RemoteTrigger tool: at once when that tool is allowed, else after `r`, which asks your permission. The
  log is read again at most every 30 seconds.
- Reads are on a timer while the pane is open; the band reads the list only while the pane is closed.
