---
name: hermes-integrations
description: Use when adding an external service or API key to Hermes.
version: 1.0.0
author: Hermes Agent + Teknium
license: MIT
metadata:
  hermes:
    tags: [hermes, mcp, integrations, api-keys, configuration]
    related_skills: [hermes-agent]
---

# Connecting external services to Hermes

## When to Use

Load when the user asks to connect a service to Hermes: "配置一个 X 的 key=...", "add <service>", "wire up <provider's> API", or any request to give the agent a new external capability (search, extraction, data source).

For "配置一个 X 的 key=..." requests: pick the right integration surface, wire the credential, and verify with a real call before reporting success.

## Procedure

1. **Check built-in providers before installing anything.** Bundled web-search providers live in the Hermes source tree under `plugins/web/` (tavily, exa, brave_free, ddgs, searxng, perplexity, xai, firecrawl, keenable, parallel, openai_native). If the service is one of these, only its `*_API_KEY` needs to go into `~/.hermes/.env` — no MCP setup.
2. **Get the service's own MCP endpoint.** For everything else, fetch the vendor's install docs — many serve a markdown setup guide at a stable URL (AnySearch: `https://anysearch.com/install/mcp-install.md`). Prefer the documented Streamable-HTTP MCP URL; skip SSE/stdio proxies unless the doc requires one.
3. **Add the server:** `yes | hermes mcp add <name> --url <endpoint> --auth header`. `hermes mcp add` is interactive (auth question, then "Enable all tools?"); piping `yes` accepts defaults and enables all discovered tools.
4. **Fix the credential in `~/.hermes/.env`.** The add writes `Authorization: Bearer ${MCP_<NAME>_API_KEY}` into config.yaml and creates the variable in .env — but a piped/absent answer at the key prompt leaves the value EMPTY or junk. Read the .env line back and write the real key in. Keys live in `.env` only, never in config.yaml.
5. **Verify live before claiming success:**
   - Handshake: `curl -s -X POST <endpoint> -H "Authorization: Bearer <key>" -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"verify","version":"1.0"}}}'`
   - Real call: `tools/call` on the primary tool with a throwaway query (e.g. a search for a known phrase) and confirm non-empty results.
6. **New sessions only.** MCP tools are discovered at session start — the current session cannot use them until `/new`. Say so when reporting done.

## Pitfalls

- After `hermes mcp add`, re-read the key's .env line — the interactive prompt can consume a piped line as the "key", leaving a one-char junk value that 401s every later call.
- If `web_search` fails or falls back to keyless backends, curl the vendor's site directly for docs instead of retrying the search backend — vendor install pages are plain fetchable HTML/MD.
- To check how a hermes CLI command actually behaves, read the source: this install is npm-based — launcher `~/.hermes/bin/hermes`, source `~/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/` (e.g. `hermes_cli/model_switch.py` for /model and alias resolution). Source is authoritative when docs and behavior disagree.
