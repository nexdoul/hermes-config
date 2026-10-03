# Triage and rotation when a target refuses this host's IP

For the case "route a service's egress elsewhere" / "rotate subscription nodes to get past a
block". This file is the triage order, the subscription → node-pool recipe, and the point at
which rotation stops being the right tool.

## The one test that decides whether to build a route

Take it *before* any tunnel, proxy or node work:

```bash
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
for u in https://www.google.com/ https://github.com/ https://<blocked-target>/; do
  printf '%s -> %s\n' "$u" "$(curl -s -o /dev/null -w '%{http_code}' \
    -x http://127.0.0.1:<mihomo-port> -A "$UA" -m 20 "$u")"
done
```

| control | target | meaning | next step |
|---|---|---|---|
| 200 | 200 | no block | stop — the earlier failure was transient |
| 200 | 403/429 | target refuses this exit's identity | a route *may* help — build it |
| 403 | 403 | the whole path is broken | fix the path, not the target |
| timeout | anything | path broken | fix the path first |

Read the refusal body when it is not obvious: `Attention Required! | Cloudflare` with
`Sorry, you have been blocked` is a target-side decision, and `error code: 1010` is the same
family keyed on the request's UA signature — which means changing the UA, not the exit.

## When rotation can and cannot work

| block type | rotation helps? |
|---|---|
| one address rate-limited or banned | yes — another node answers |
| WAF rule on the provider's **ASN / address range** | **no** — the whole pool is refused |
| geo restriction | yes, if the pool holds a clean region |
| site-wide challenge keyed on this UA | no — change the UA |

Confirm the range case by sweeping **the entire pool**, not a sample: a handful of failures
looks like bad nodes and invites a retry. Two subscriptions swept node-by-node (21 + 34
nodes) all returning 403 while the control returned 200 *on those same nodes* is what
settles it — nothing short of the whole-pool count convinces.

Expect a range-blocked sweep to be fast and uniformly refused: healthy nodes answer in
~0.3–0.5s with a 403. Slow or timing-out nodes are a path problem, a different symptom.

## Recipe: subscription → mihomo node pool

1. **Fetch and decode.**
   `curl -sS -o /tmp/sub.txt '<subscribe-url>' && base64 -d /tmp/sub.txt > /tmp/sub.yaml`.
   A subscription is almost always a base64 **URI list** (`vless://`, `hysteria2://`,
   `trojan://`, `ss://`), NOT a Clash yaml — never hand it to mihomo as a config file.
2. **Parse each URI into a mihomo proxy dict.** Per protocol the fields that matter:
   - `vless` — server, port (strip a trailing `/` some providers append), uuid, `tls: true`,
     `servername`/`sni`, `network: ws` plus its `ws-opts` path, `client-fingerprint`.
   - `hysteria2` — server, port, password, `sni`, `skip-cert-verify`, obfs fields if present.
   - `trojan` — server, port, password, `sni`, `skip-cert-verify`, `ws` transport + path.
   Decode the `#fragment` with URL quoting for the display name; names are percent-encoded
   (`%E9%A6%99%E6%B8%AF01` = `香港01`). Write the result as `proxies: [...]` in its own file.
3. **Filter to real nodes before loading.** Providers publish status text
   (`剩余流量：…`, `官网：…`) as pseudo-entries that resolve to one shared server, inflating
   the pool. Keep only names carrying a region token (the flag emoji plus the CJK spelling)
   and re-count.
4. **Apply the standing regional exclusions.** This user's provider has its JP and KR nodes
   blocked provider-side — "日本和韩国节点都被屏蔽，不用尝试" — so drop them at parse time
   rather than letting the group select one and report a failure nobody asked for.
5. **Wire the group as `url-test`, not `select`.** `select` needs an operator re-pick after
   every block; `url-test` re-probes every `interval` seconds and moves on by itself:

```yaml
proxy-providers:
  <name>:
    type: file
    path: <name>.yaml
proxy-groups:
  - name: <GROUP>
    type: url-test
    use: [<name>]
    url: 'https://www.gstatic.com/generate_204'
    interval: 180
    tolerance: 50
```

6. **Verify what loaded from the controller, not from the config.**
   `curl -s --noproxy '*' http://127.0.0.1:9090/proxies/<GROUP>` and compare `len(all)`
   against the provider file's node count — a mismatch means pseudo-nodes got through or the
   provider `path` is wrong. `127.0.0.1` probes need `--noproxy '*'` whenever the ambient
   `http_proxy` is set, or the probe egresses and fails with `Empty reply from server`.

## The whole-pool sweep

`url-test` rejects `PUT /proxies/{group}` selection, so add a **temporary** `select` group
over the same provider, sweep, then remove it:

```bash
GRP=SWEEP
now_() { curl -s --noproxy '*' http://127.0.0.1:9090/proxies/$GRP \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("now") or "")'; }
CONTENT='<a string only the target emits>'
for n in $(curl -s --noproxy '*' http://127.0.0.1:9090/proxies/$GRP \
  | python3 -c 'import sys,json;print(" ".join(json.load(sys.stdin)["all"]))'); do
  curl -s --noproxy '*' -X PUT -H 'Content-Type: application/json' \
       -d "{\"name\":\"$n\}" http://127.0.0.1:9090/proxies/$GRP >/dev/null
  # 204 does not mean the switch took: read `now` back or the sweep lies
  [ "$(now_)" = "$n" ] || { printf 'MISMATCH|%s\n' "$n"; continue; }
  body=$(curl -s -x http://127.0.0.1:7890 -A "$UA" -m 25 "https://<target>/")
  # a refusal page carries <title> and <!DOCTYPE html> too — match content, not markup
  case "$body" in
    *"Sorry, you have been blocked"*|*"Attention Required"*) code=BLOCKED ;;
    *"$CONTENT"*)                                         code=OK ;;
    *)                                                    code=NONE ;;
  esac
  printf '%s|%s\n' "$code" "$n"
done | tee /tmp/sweep.txt
grep -c '^OK|' /tmp/sweep.txt   # the GOOD count is the conclusion
```

Run it once and stop. A sweep that returns zero 2xx answers *is* the finding; re-running it
hopes for a different pool and burns the round. Also pin down the target's resolved real IP
(`DoH` through the egress proxy) and try `curl --resolve` before concluding — a
content-addressable refusal is not the same as an IP-range refusal.

The count is only evidence if every iteration actually switched nodes. An `url-test` group
rejects `PUT` selection outright, and even a `select` group can answer `204` without moving
`now`; a sweep that silently re-measures one node N times produces a uniform result that
reads exactly like a range block. Assert `now == <requested node>` per iteration, and treat a
non-zero `MISMATCH` count as "the sweep did not run" rather than as extra blocked nodes.

Before sweeping, check the nodes are even reachable in this environment: a host with no UDP
egress cannot dial a QUIC-based protocol at all, and a host with IPv6 disabled cannot reach a
node whose only address record is AAAA — those nodes are structurally absent, not blocked, and
they should be dropped at parse time so the sweep's denominator is honest. Also do not conflate
"the node dials" with "the target accepts us": an outbound TCP handshake to the node that
returns a *different host's* TLS certificate means the path is MITM'd and no proxy protocol
that verifies a name can complete on it.

When the pool is inert because its host is behind NAT (every node SNAT's to the host's own
address), node selection cannot change egress identity and no sweep of it can prove anything
about the target. Detect that by comparing the echo IP across two different selections first;
if unchanged, the pool is not the lever, and the question becomes "which exit *can* we reach,
and can the fetch run there".

## After the sweep

- **Leave the group on `url-test` even when every node is blocked.** It costs nothing and
  recovers by itself the day the block lifts, with no operator step and no stamp to clear.
- **Restore the real target config** afterwards — point the group back at the subscription
  the user gave, not at whatever was being tested, and restart the service so the loaded
  pool matches the file.
- **Record the negative result where the owning project's rules live** (the project's
  `AGENTS.md` or its skill) so the next session does not repeat the sweep, and note which
  non-datacenter exit would be needed to actually get past it.
