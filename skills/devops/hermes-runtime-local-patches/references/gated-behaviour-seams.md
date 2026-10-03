# Seams for adding a gated behaviour to the Hermes runtime

Topical companion to `Procedure: Add a Gated Runtime Behaviour`. Covers where a conditional
behaviour hooks into the runtime, and the trap at each seam. Verified against the
full-trust-delegation work (trigger-phrase gated self-approval).

## The two blocking seams

| Seam | File | Why here |
|---|---|---|
| Clarify wait | `gateway/run_turn_runner_clarify_delivery.py` (`_clarify_send_then_wait`) | The one place a question blocks the agent thread; gateway, CLI and TUI all reach it |
| Approval wait | `tools/approval_gateway_wait.py` (`_await_gateway_decision`) | The one place a dangerous command blocks; shared by terminal, execute_code, plugin and MCP gates |

Both are worth knowing before designing anything: the gate is already there, so the work is
usually "decide whether to answer it myself", not "find a way to stop asking".

### Clarify seam traps

- **The global timeout is the fallback, not a default.** `clarify_mod.get_clarify_timeout()`
  resolves `clarify.timeout` / `agent.clarify_timeout`, default 3600. Capture its value and pass it
  as the override layer's fallback (see `Pitfalls`), or ungated sessions see a different window.
- **`<= 0` means "do not block at all"**, distinct from `None` ("use the global window"). Keep both
  meanings separate: conflating them turns a misconfigured value into an unbounded block.
- **Clear the registration when you answer a prompt nobody is waiting for.** Leaving the entry
  armed means a late tap resolves a hung waiter the agent already abandoned.
- **Reuse the canonical timeout sentinel.** `tools/clarify_tool.py::TIMEOUT_RESPONSE` already tells
  the model to use its best judgement; a new sentinel would need every surface taught to recognise it.

### Approval seam traps

- **Bypass after the queue append, before `notify_cb`.** Appending first keeps the concurrent-batch
  and terminal-approval machinery seeing the same lifecycle as a real prompt; dropping the entry
  after it means no card is ever sent and nothing is left for `/approve` to find. A pre-hook still
  fires, so plugins and observers see the lifecycle.
- **Auto-approving returns a one-shot scope, never `session`/`always`.** Delegation covers one turn;
  a persisted choice would quietly outlive it.
- **Irreversibility survives the gate.** Convenience must never unlock a destructive command; the
  guard list makes the gate a bet on reversibility, not a blanket allow.

## Registry state that gates blocking prompts

Store the per-turn window somewhere surfaces already reach by `session_key` — beside the clarify
entries in `tools/clarify_gateway.py` is the natural home, since that module is already the sync
queue the agent thread blocks on and every surface imports it.

- **Teardown must clear it.** Extend the existing `clear_session` (`/new`, shutdown, agent eviction)
  so the next turn of the same key is supervised again; a leaked window silently disables
  supervision for every later turn.
- **Store the intent beside the window.** Gating an irreversible-allow separately means two
  session-keyed lookups that can disagree; keep the pair in one registration call.
- **`session_key` is `Optional` on the gateway's turn context.** Guard the registration — a `None`
  key cannot be delegated, and registering under `""` collides every session that also lacks one.

## Prompt injection

Guidance blocks assemble in `agent/system_prompt.py::_guidance_parts`. Add the gated block there,
reading the policy object the turn runner attached to the agent, so the prompt follows the same
decision the runtime enforces. Return `None` for the ungated case — the block is then absent and the
supervised system prompt stays byte-identical.

A cache-friendly agent may predate the attribute; `getattr(agent, ..., None)` keeps the prompt
build from raising.

## CLI parity

The CLI has its own turn entry (`hermes_cli/cli_chat_turn_mixin.py::_chat_run_agent`) and its own
callback (`hermes_cli/cli_modal_mixin.py::_clarify_callback`). Register the same policy there, beside
the existing session-key binding, or the CLI keeps prompting while the gateway delegates.

- **Read the session key from the CLI object** (`self.session_id`); do not invent a constant on
  the registry module to hold it. Grep the mixin for the field's real name before writing it
  (`grep -n 'self.session_id' hermes_cli/cli_modal_mixin.py`) — a plausible-looking invented name
  compiles fine and silently registers nothing.
- **Keep the original method signature.** Replacing positional parameters with defaults while
  "cleaning up" a neighbouring call is how callers break.

## Seam: a reminder that crosses sessions

The user mutes every window but one, so a milestone from any other session has to reach the watched
one. Nothing blocks here; the seam is a send, and the traps are about routing rather than waiting.

| Seam | File | Why here |
|---|---|---|
| Turn end | `gateway/run_turn.py` (`_run_agent_stamp_heartbeat_terminal`) | Every turn finalises through it, and the completed/waiting/stopped decision already exists |
| Turn start | `gateway/run_turn_runner.py` (`_wire_turn_agent_callbacks`, beside the autonomy registration) | The one place every turn already passes, and where session_key + user_config are both in hand |
| Danger | `tools/approval_gateway_wait.py`, after the delegation bypass falls through | An irreversible command still escalates under delegation, so this is the exact point where a card nobody will read appears |

### Traps

- **Derive "completed" from `final_response`, not from absent failure flags.** The two failure markers
  do not partition the space: a blocked or aborted turn arrives as a dict with neither flag set and no
  answer text. Reading the answer field makes that case silent, which is what it is.
- **Route through the gateway's existing synthetic-event injector** (`_inject_watch_notification`), not
  through an adapter you resolved yourself. Its `_build_process_event_source` needs
  `platform` + `chat_type` + `chat_id`, and `chat_type` cannot be parsed out of a session key — capture
  all three at claim time via `_parse_session_key` and store them beside the claim.
- **A blank override key must fall through to the claim.** Overriding with an empty string matches
  nothing and silently disables every reminder; force the value non-empty before treating it as
  authoritative, and keep `is_main_session(None)` false so a missing key never becomes the target.
- **Announce the watched session's own events nowhere.** Injecting a reminder into the session that is
  already displaying the output duplicates it; check identity first, before resolving any target.
- **A reminder runs on the agent thread and must never block it.** `run_coroutine_threadsafe` when a
  running loop is reachable, `coro.close()` otherwise, and every path wrapped so a delivery failure
  cannot take the finalised response down with it.
- **Verify the injection signature from the source before wiring it.** Reading
  `_build_process_event_source` is what reveals the three-field requirement; guessing a routing dict
  compiles cleanly and drops the message with only a debug log.
- **Dedupe identical consecutive summaries.** A quiet session that emits the same line twice is noise,
  not a new milestone.

See `Procedure: Notify One Watched Session Across Sessions` in SKILL.md for the ordered steps.

## Verifying a gate

- One file for the decision function (trigger matching, modes, irreversibility, malformed input) and
  one for the blocking-seam integration (card suppressed, queue drained, fail-closed on a broken
  registry).
- Speed up the supervised path with `monkeypatch.setattr` on the timeout getter so a test proves
  "waits as before" in seconds instead of minutes.
- Regressions in the seam's own existing test file are the strongest signal that the gating
  mechanism is wrong — run those files, not only the new ones.

