# AnySearch MCP integration

Search infrastructure for AI agents. Configured on this deployment as MCP server `anysearch`.

## Endpoint & tools

- MCP endpoint: `https://api.anysearch.com/mcp` (Streamable HTTP, no stdio proxy needed)
- 4 tools: `search` (default web search), `batch_search` (parallel queries in one call), `extract` (URL → full-page markdown; their docs position it as the default extractor), `get_sub_domains` (vertical-domain discovery)
- Docs: https://anysearch.com/install/mcp-install.md

## API key

- Optional — anonymous access works at lower rate limits. Key format `as_sk_...`; default rate limit 100 req/min.
- On this deployment the key lives in `~/.hermes/.env` as `MCP_ANYSEARCH_API_KEY`, referenced by `mcp_servers.anysearch.headers` as `Authorization: Bearer ${MCP_ANYSEARCH_API_KEY}`.
- Need a new key? The docs define a single-call email-registration API (`POST /v1/auth/email/register`) that returns the key once, or the user can create one at https://anysearch.com/console/api-keys.

## Connectivity probe (validated)

Handshake:

```bash
curl -s --max-time 25 -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"probe","version":"1.0"}}}'
```

A healthy reply carries `serverInfo.name: anysearch-mcp-server`. Then a real call — a healthy `tools/call` of `search` returns `content[0].text` with `## Search Results` markdown.

Use this probe to separate key-authentication failures from endpoint outages before telling the user anything is broken.
