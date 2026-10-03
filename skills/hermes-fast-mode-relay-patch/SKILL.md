---
name: hermes-fast-mode-relay-patch
description: "Use when Hermes update breaks /fast on sub2api relay."
version: 1.0.0
tags: [hermes, patch, fast-mode, service_tier, relay]
---

# Hermes Fast-Mode Relay Patch (sub2api)

## Why
Hermes hard-gates fast mode (`service_tier: "priority"` / Anthropic `speed: "fast"`) to first-party hosts only. User's models all route through the relay `sub2api.riu.edu.kg` (providers: dsh-mysub-oc / dsh-mysub-oai / dsh-mysub-pro / dsh-step / dsh-mysub-free), so `/fast` was a no-op. The model-side whitelist (`_OPENAI_FAST_MODE_PREFIXES` in `hermes_cli/models_catalog_static.py`, `gpt-` prefix) already matches gpt-6-* — only the endpoint gate blocks.

## What to patch
File: `<hermes install>/hermes_cli/models.py` — npm installs use
`/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/hermes_cli/models.py`.

Function `_fast_mode_route_supported(model_id, provider, base_url)`. AFTER the `allowed = {...}` if/elif chain, BEFORE the `if provider and normalize_provider(provider) not in allowed` check, insert:

```python
    # User-added: third-party relay endpoints that forward service_tier/speed params upstream.
    _host = (urlparse(str(base_url or "")).hostname or "").lower()
    if _host == "sub2api.riu.edu.kg":
        return provider in allowed or normalize_provider(provider) in allowed or provider in {
            "dsh-mysub-oc", "dsh-mysub-oai", "dsh-mysub-pro", "dsh-step", "dsh-mysub-free"}
```

Gotcha: compute `_host` inside the inserted block (the original code parses `host` only later); don't reference `host` before assignment.

## Verify
```python
from hermes_cli.models import _fast_mode_route_supported, resolve_fast_mode_overrides
assert _fast_mode_route_supported('gpt-6-luna', 'dsh-mysub-oai', 'https://sub2api.riu.edu.kg/v1')
assert resolve_fast_mode_overrides('gpt-6-luna', provider='dsh-mysub-oai', base_url='https://sub2api.riu.edu.kg/v1') == {'service_tier': 'priority'}
assert not _fast_mode_route_supported('gpt-6-luna', 'dsh-mysub-oai', 'https://other.example.com/v1')
```
Run from the install root dir so imports resolve. New sessions only — running sessions keep old code.

## When to re-apply
`hermes update`, npm reinstall, or runtime refresh overwrites models.py. Symptom after update: `/fast fast` says "only available for models that support fast mode" or fast flag silently ignored on relay routes.

**2026-09-27: hermes-start auto-reinstall wiped the runtime tree mid-session (container restart healing). Patch re-applied same session. Symptom: terminal `cd` to runtime dir fails + `grep User-added` empty. Hermes CLI path after reinstall: `<runtime>/venv/bin/hermes` (the `~/.hermes/bin/hermes` symlink may lag). Re-apply = insert block via patch tool, then venv-python verify. Default model is now dsh-mysub-oai-fast/gpt-6-luna with `agent.reasoning_effort: max` (user request).

## Caveat (told to user 2026-09)
Whether sub2api actually forwards `service_tier` upstream unverified — param may be ignored upstream without error. Also unknown: whether sub2api bills extra for priority.

## gpt-6-luna fast-by-default (config, NOT source patch — survives updates)
User wanted luna always fast, other models never. Done via config in `~/.hermes/config.yaml`, no code edit:
1. New provider entry `dsh-mysub-oai-fast` (same base_url/key_env as dsh-mysub-oai) with `model: gpt-6-luna` + `extra_body: {service_tier: priority}`.
2. Alias `6luna: dsh-mysub-oai-fast/gpt-6-luna`.
Key mechanism: `providers:` entries support `extra_body` (valid field in `_KNOWN_PROVIDER_KEYS`); `_apply_custom_provider_extras` in `hermes_cli/runtime_provider_custom.py` lifts it to `request_overrides.extra_body` at provider RESOLUTION time (no `custom:` prefix matching needed — that's a different, init-time path). Model scoping: entry has `model:` set so only that model matches (`_custom_provider_model_matches`).
Verify: `resolve_runtime_provider(requested='dsh-mysub-oai-fast', target_model='gpt-6-luna')['request_overrides'] == {'extra_body': {'service_tier': 'priority'}}`; original provider + other 4 providers return None. Use the hermes venv python (`runtime/hermes-agent/venv/bin/python3`), not system python3 (no httpx).

## Related config (unrelated to patch, kept for context)
- Model aliases live in `model.aliases` in `~/.hermes/config.yaml` (20 set: 6astra/6sol/6luna/dsf/gf + 15 free-pool bare names). `hermes config set model.aliases.X` mangles dotted names into nested keys — write flat YAML via python instead, then `python3 -c "import yaml; yaml.safe_load(open('...'))"` to validate.
- MCP `anysearch` configured (search/batch_search/extract/get_sub_domains), key `MCP_ANYSEARCH_API_KEY` in `~/.hermes/.env`.
