---
name: hermes-model-config
description: "Use when switching Hermes models, aliases, or MCP servers."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, models, aliases, mcp, anysearch]
    related_skills: [hermes-agent]
---

# Hermes model & tool-server configuration (this deployment)

## When to Use

Load when the user asks to switch models, set up model aliases, or configure/verify an MCP tool server (e.g. AnySearch) on this Hermes deployment.

## Source of truth

- Read the active `~/.hermes/config.yaml` under `providers:` for provider IDs and model availability, and `model.aliases` for shortcuts. Do not rely on remembered provider rosters, defaults, or alias targets: this deployment can change. Avoid printing credentials while inspecting config; provider secrets belong in `~/.hermes/.env`.

## Switching models

- In chat: `/model <alias>` or `/model provider/model`. Session-scoped by default; add `--global` to persist as default. Verify with `/status`.
- Cross-provider switches need the full `provider/model` form — each provider authenticates with its own key, so a bare model name alone cannot cross pools.

## Alias scheme (user's standing convention)

- Inspect the live `model.aliases` before relying on or changing any mapping; aliases and provider targets can change.
- Current dot-free shortcuts: `6astra` → `dsh-mysub-pro/gpt-6-astra`, `6sol` → `dsh-mysub-oai/gpt-6-sol`, `6luna` → `dsh-mysub-oai-fast/gpt-6-luna`, `dsf` → `dsh-mysub-oc/deepseek-flash`, `gf` → `dsh-mysub-oc/glm-5.3-flash`, `step5` → `dsh-mysub-free/step-5-preview`, and `step7f` → `dsh-mysub-free/step-3.7-flash`.
- Every `dsh-mysub-free` model is ALSO aliased by its bare name (`model.aliases.<full-name>: dsh-mysub-free/<full-name>`), so `/model <full-name>` resolves to the free pool for models that exist in several pools — the user's explicit default.
- Alias values are `provider/model` strings under `model.aliases:`. To add a shortcut, first confirm the exact target exists under that provider in the active config and the alias is unused; then use `hermes config set model.aliases.<dot-free-alias> <provider>/<model>`. Parse the saved config and verify the exact mapping and that existing aliases remain unchanged. This registers the alias; it does not change the global default model.

## Pitfall: dotted alias names vs `hermes config set`

- `hermes config set model.aliases.<name>` splits the NAME on dots into nested YAML keys — `glm-5.3-200k` lands as `glm-5: {3-200k: ...}` and silently never resolves. Use dot-free alias names only.
- For dotted bare-name aliases, edit `config.yaml` directly: the `patch` tool refuses Hermes config files, so use a Python read/replace (needs user approval for the heredoc) and validate afterwards with `python3 -c "import yaml; yaml.safe_load(open(...))"`. After any alias batch, grep for mangled leftovers (a top-level key like `glm-5:` with an indented `3-200k:` child) and flatten them.

## Adding an MCP tool server (AnySearch pattern)

1. `hermes mcp add <name> --url <endpoint> --auth header` — interactive; pipe `yes` into it to accept the discovered tool list.
2. Pitfall: the API-key prompt is a getpass read that consumes one piped line, so the generated `MCP_<NAME>_API_KEY` in `~/.hermes/.env` ends up as garbage (observed: the literal `y`). Always overwrite that line with the real key afterwards and verify the stored value before trusting it.
3. MCP tools load only in NEW sessions — tell the user to start one; do not expect them in the current session.
4. Verify the endpoint directly with a curl JSON-RPC `initialize` + `tools/call` probe before reporting success (see references/anysearch.md).

## Environment note

- This sandbox's DNS resolves every domain to fake-IPs in 198.18.0.0/16 (transparent egress proxy). Never judge reachability from `getent`/`dig` output — probe with `curl` and judge by HTTP status.
