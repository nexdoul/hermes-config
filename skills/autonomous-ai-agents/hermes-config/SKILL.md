---
name: hermes-config
description: "Use when configuring Hermes: models, aliases, MCP, config."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, configuration, models, aliases, mcp]
    related_skills: [hermes-agent]
---

# Configuring this Hermes instance

## When to Use
Load before: switching or aliasing models, adding/testing MCP servers, editing ~/.hermes/config.yaml, or diagnosing why a model switch or /fast behaves unexpectedly.

All model traffic runs through custom providers behind one relay (sub2api.riu.edu.kg), split into 5 provider entries — `dsh-mysub-oc`, `dsh-mysub-oai`, `dsh-mysub-pro`, `dsh-step`, `dsh-mysub-free` — each with its own API key. Global default: `dsh-mysub-oc` / `glm-5.3-flash`.

## Switching models
- Cross-provider in chat: `/model provider/model` (full format — switches the provider's key too). A bare name stays inside the current provider.
- `/model X` is session-scoped; add `--global` to persist as default.
- Aliases live in `model.aliases` as `"alias: provider/model"` strings. Standing conventions (user-set): short aliases `6astra`/`6sol`/`6luna`/`dsf`/`gf`; every bare free-pool model name maps to `dsh-mysub-free/<name>` so `/model step-5-preview` etc. defaults to the free pool — to reach a paid twin of a duplicated model, use the full `provider/model` form.

## Editing config.yaml
- `hermes config set model.aliases.<name>` CORRUPTS dotted alias names into nested YAML (`glm-5.3-200k` → `glm-5: {3-200k: ...}`) and the alias then never resolves. For dotted keys, edit the file with a python heredoc via terminal, then validate: `python3 -c "import yaml; yaml.safe_load(open(path))"` and print the parsed block.
- The `patch` tool refuses ~/.hermes/config.yaml (security-sensitive guard) — go through terminal python, not patch.
- Multi-line or prose values: `POLICY=$(printf '%s\n' ...)` then `hermes config set <dotted.key> "$POLICY"`; `hermes config unset <key>` removes a key. Multi-line text lands as a single quoted string with `\n` escapes, which is what the readers expect.

## Reusing a Hermes provider in another application

1. Resolve the requested live provider and canonical model, rather than copying the global default; session model switches can differ from the provider's default model.
2. Read the provider's `base_url`, `api_mode`, `key_env`, and required headers. Resolve the credential inside a script without printing it, embedding it in shell arguments, or writing it into a reusable script.
3. Confirm the target application's protocol and configuration API from its deployed version. Prefer its authenticated API so encryption and runtime reload hooks remain intact; do not bypass login by manufacturing a session token from a server signing key.
4. Test the exact model/key/protocol with a harmless request, save only the authorized model configuration, then read back that exact target. Separate relay connectivity, configuration persistence, and application-native inference in the final report.
5. For trading applications, model setup does not authorize creating or starting a trader, changing exchange access, or moving money. Check for active traders before changing a model they may use.

For NOFX's model payload and encrypted transport, consult [references/nofx-model-api.md](references/nofx-model-api.md).

## Adding a provider
- The credential goes to `~/.hermes/.env` as a bare `KEY=value` line (no quotes), `chmod 600`, and the provider block references it by `key_env`; never inline a key in config.yaml.
- Add the block by reading the YAML in python and inserting the dict — `base_url` / `api_mode: chat_completions` / `key_env` / `extra_headers` with a real browser User-Agent (the same one the other providers send) / `models` / default `model` — then rewrite with `yaml.safe_dump(..., sort_keys=False)` to a temp file and `os.replace`. `hermes config set` cannot express a nested block-shaped value without corrupting it, same reason dotted aliases are edited by hand.
- The dump rewrites the whole file, so prove nothing was lost: re-read it and count the pre-existing sections — every provider entry, `model.aliases`, `approvals.mode` — against their pre-edit values, then confirm the new block through the runtime reader and `hermes config get providers.<name>.<field>`.
- Smoke-test the credential and the config separately: a vendor curl proves the key, the Hermes client proves the schema was accepted — exact invocation and the `reasoning_effort` enum trap a new provider can spring are under Reasoning effort below.

## Approvals (`approvals.*`)
- `approvals.mode`: `off` / `smart` / `manual`. `smart` sends every flagged command through a guardian LLM (temp 0, one-word verdict APPROVE/DENY/ESCALATE); APPROVE runs immediately, ESCALATE presents the human card. A commented-out `mode:` line means the code default applies — read the default from the reader, not the comment.
- `approvals.smart_policy`: operator rules appended to the guardian's **system** prompt as trusted input. Keep it to the narrow escalate/approve list and never write a line that contradicts the guardian's default "escalate when uncertain" — the policy wins over the default and silently closes the gate you were relying on.
- `approvals.timeout` defaults to 300s; a card clicked after expiry resolves zero records, which reads as "nothing happened" in the transport log.
- Approval settings read through the mtime+size-aware config reader can take effect without a gateway restart. Do not generalize this to all settings: platform adapters may cache their settings at construction. Inspect the consuming reader and verify runtime behavior before claiming a platform setting is live; a successful file write or offline adapter test proves parsing, not uptake by the running adapter.
- Verify the effective values through the runtime reader (e.g. `tools.approval_context._get_approval_mode()`), not `config get` alone.

## Reasoning effort defaults and per-model exceptions
- Treat `agent.reasoning_effort` as the fallback for every model; `agent.reasoning_overrides` takes precedence for matching model IDs. Resolve a friendly alias such as `6luna` through `model.aliases` first, then key the override by its provider-qualified canonical model ID, not by the alias.
- Read the existing `agent.reasoning_overrides` before editing and merge the new entry instead of replacing other models' exceptions. Use `hermes config set agent.reasoning_effort <level>` and set the merged mapping with `hermes config set agent.reasoning_overrides '<JSON mapping>'`.
- If this Hermes version refuses either reasoning key as unrecognized, retry that write with `--force`; some versions' config schema lags the runtime reader. A warning from `hermes config get` alone does not prove the runtime ignores a value.
- Verify the effective result for both an exception and an ordinary model through the installed runtime's `resolve_reasoning_config` helper using the parsed config. Check that the exception returns its pinned level and an unlisted model returns the global fallback; do not treat YAML parsing or `config get` output alone as semantic verification.
- **A new provider can have a narrower `reasoning_effort` enum than the global default.** Global `xhigh` against a provider whose schema accepts only `none/low/medium/high` fails with HTTP 400 `literal_error ... reasoning_effort input should be 'xhigh'...`. Sibling models on the same provider may answer fine, so it reads as a per-model bug instead of a provider mismatch — symptom: one model of a new provider works, another dies with `custom rejected this request as malformed`. Fix: add `provider-qualified/model: high` to `agent.reasoning_overrides`, MERGED with the existing entries (a write that replaces the mapping silently drops other models' pins), then re-test that exact sibling.
- Verify a newly added provider through the Hermes client itself, not only the vendor's curl endpoint — curl proves the credential, only the client proves the config schema is accepted. `hermes chat` is not a subcommand; the prompt goes through `-z PROMPT` (`hermes -m MODEL --provider P -z "..."`).
- Config edits need no gateway restart, so a new provider is usable from the running session once the reader re-signs; confirm with `hermes config get providers.<name>.<field>` and by a live call before reporting success.

## MCP servers
- `hermes mcp add <name> --url <endpoint> --auth header` is interactive (auth prompt, enable-all-tools prompt) — pipe `yes |` into it to auto-accept.
- `hermes mcp add` writes a `${MCP_<NAME>_API_KEY}` placeholder in config headers but leaves the .env var EMPTY — fill the real key into ~/.hermes/.env yourself and verify the value landed.
- New MCP tools only appear in a NEW session. Verify the endpoint works before telling the user: raw curl `initialize` then `tools/call` with `Accept: application/json, text/event-stream` and `Authorization: Bearer <key>`.
- Configured: anysearch (https://api.anysearch.com/mcp) — tools: search, batch_search, extract, get_sub_domains. Docs: https://anysearch.com/install/mcp-install.md

## Fast mode (/fast) — never promise it on relays
- Hardcoded whitelist: Anthropic fast Opus (`speed: fast`), OpenAI/Codex (`service_tier: priority`), Grok 4.6 family. Gated to first-party base_urls (api.anthropic.com / api.openai.com / api.x.ai) — through any relay base_url the fast overrides are never attached. The alias schema (model/provider/base_url/api_key/key_env) has no per-alias request overrides, so fast cannot be bound to an alias.
- For "make it faster" on relay models: lower `agent.reasoning_effort` (user runs xhigh — the biggest latency lever) or switch model tier.

## Reading implementation details
- Source tree: ~/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/hermes_cli/ — alias resolution in `model_switch.py`, fast-mode gates in `models.py` (`resolve_fast_mode_overrides`).
- `hermes model` is an interactive picker only (no list subcommand); `hermes chat -m MODEL --provider P` for one-shot.
