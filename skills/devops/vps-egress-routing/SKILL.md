---
name: vps-egress-routing
description: "Route a service's egress through a user-owned VPS."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [vps, ssh, tunnel, socks5, egress, proxy, 115, migration, localization]
    related_skills: [hermes-runtime-local-patches, stealth-search-collect, camofox-selfheal-deploy]
---

# Route a service's egress through a user-owned VPS

A service (115网盘, JavDB, an API client) must be reached so the remote side sees a
specific IP — usually a residential/cloud IP in the user's own VPS fleet, not the sandbox
egress. This skill covers the tunnel, the wrapper that makes the tunnel mandatory, how to
PROVE the egress IP is the one you intended, and migrating a project that ran on the VPS
so it runs on this host.

## When to Use

- Any request of the form "my request to X must come from my VPS" / "115 看到的 IP 要是 CN IP".
- A project relocated from a remote VPS cannot run locally (arch mismatch, hardcoded paths).
- A service is geo/ASN-blocked and must be reached through a specific node.
- You need to verify an SSH tunnel / SOCKS5 proxy actually carries the traffic.

Do not use for browser scraping (see `stealth-search-collect`) or for Hermes runtime patches
(see `hermes-runtime-local-patches`).

## Always-on rules

- **Prove the egress IP by comparing exit IPs, never by trusting a proxy flag.** The only
  acceptable proof: an echo service (`https://myip.ipip.net/`) fetched *through* the tunnel,
  next to the *same* fetch through the sandbox egress as a control. Two lines, two IPs.
  The sandbox-side control will normally return a *different address on every attempt*
  (see the rotation fact below) — that variation is the pool rotating, not a broken control,
  and it makes the pinned route easier to identify, not harder.
- **A browser needs its proxy passed to the launcher, and needs its exit proven from inside
  the browser.** Browsers ignore the ambient `http_proxy`/`https_proxy`/`no_proxy` variables,
  so passing a proxy "by environment" silently egresses the browser from the sandbox pool.
  Hand the proxy to `launchOptions`/`launchPersistentContext` explicitly, then navigate to an
  IP echo page and compare the body against the expected exit before any state-changing action
  — abort on mismatch rather than continue on the assumption the flag was honoured. A remote
  proxy reached over an SSH `-D` is SOCKS5; a Firefox/Playwright launch wants an HTTP proxy,
  so bridge it locally rather than feeding the SOCKS port to the browser.
- **A target's refusal needs its stage identified before its cause.** The same wall can be
  reached at two very different points: refused *before* the profile form (name/birthday) is
  shown is an exit-identity/reputation decision, while accepted through registration and then
  landed on an "unavailable in your region" screen is an exit-geography decision. They look
  identical in a log that records only the final URL — record the last screen's body text and
  the furthest form actually reached, or the wrong variable (age, email domain, locale) gets
  blamed.
- **A wrapper must unset the ambient proxy vars before exporting its own.**
  `unset http_proxy https_proxy all_proxy no_proxy` then `export HTTPS_PROXY=socks5h://...`.
  If you only add to them, an inherited `HTTP_PROXY` silently wins and the traffic egresses
  from the wrong place.
- **The routing wrapper is fail-closed.** Probe the tunnel first; on failure exit non-zero
  (69 for "service unavailable"). Never fall back to a direct connection — a wrong-IP
  request to a storage service can create duplicate tasks or get the account flagged.
- **The proxy-env unset belongs to the wrapper, not the caller.** Callers cannot be relied
  on to clean their environment, and the caller that forgets is the one that gets caught.
- **VPS SSH needs an IP exception from the sandbox proxy.**
  `export no_proxy='<vps-ip>' NO_PROXY='<vps-ip>'` before every `ssh`/`scp` to a user-owned
  host; otherwise the transparent proxy resets the SSH handshake
  (`kex_exchange_identification: read: Connection reset`).
- **Run the verification as an HTTP request, not a ping.** Ping proves nothing about which
  IP the *target service* observes.
- **Lead the work report with a compact status table** (done / pending / blocked) and
  a short "what the target now sees" line. Narration of the debugging trail goes in
  the skill and the logs, not the reply.
- **Prove a block is per-IP before building a route.** Take the control probe *before* any
  tunnel or node work: fetch the known-good third-party hosts through the very same path
  while the target refuses. A 200 control beside a 403 target says the target is refusing
  this exit's *identity*, so a route is worth building; a 403 control says the path itself is
  broken and a route fixes nothing. It costs two curls and decides whether an hour of route
  work should start.
- **Node rotation defeats a per-IP wall, never a per-ASN wall.** Every node in one subscription
  shares that provider's address range, so a WAF rule aimed at the datacenter ASN refuses all
  of them equally. Rotate when one address is rate-limited or banned; when every node in the
  pool is refused while the control is 200, the block is on the range and the answer is a
  different *kind* of exit (residential), not another node. Confirm by sweeping the entire
  pool once — a few failed nodes look like bad nodes; the whole-pool count is the evidence.
- **Prove a selection took effect before believing any measurement that depends on it.** A
  controller that answers `204` to a node switch can leave the group pointing where it was,
  so the "sweep" becomes the *same node measured N times* and its count is fiction — the same
  class of error as the exit-IP rule above, one level down: the flag is not the proof. Read the
  group's `now` back after every `PUT`, and drop or re-flag any iteration where it did not
  move. `MISMATCH` rows in a sweep are findings, not noise to be filtered out.
- **Never read a response's identity out of its markup.** Cloudflare's refusal page
  (`Sorry, you have been blocked`, `Attention Required! | Cloudflare`) carries `<title>` and
  `<!DOCTYPE html>` exactly like the target's real page, so a `grep -o '<title>'` reports a
  blocked fetch as success and manufactures a healthy count. Match a content marker only the
  target emits, and test for the refusal string *first* so the block case is decided before
  the success case.
- **Run the fetch on the VPS; do not try to pull the VPS's proxy back here.** An SSH `-L`
  tunnel that maps a remote proxy to a local port does not put an application's request on
  the remote network: the host's transparent proxy intercepts outbound traffic *including
  loopback ports*, and unsetting every `http_proxy`/`https_proxy`/`all_proxy` variable does
  not change it — the request still egresses from here. SSH itself reaches the VPS because of
  the per-IP `no_proxy` exception, so the reliable shape is `ssh <alias> "curl ... "` with the
  work executed remotely and this host acting as dispatcher. Choose the tunnel direction
  before building anything: `-L` is for a service the VPS must reach *here*.

## Procedure

### 1. Establish the tunnel

```bash
export no_proxy='<vps-ip>' NO_PROXY='<vps-ip>'
ssh -i ~/.ssh/<alias> -N -D 127.0.0.1:<port> -o BatchMode=yes \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 -o ConnectTimeout=15 <alias>
```

Put the host in an ssh config so later commands name an alias, not an IP:

```
Host cnvps
    HostName <vps-ip>
    Port 22
    User root
    IdentityFile ~/.ssh/alias_cnvps_ed25519
    IdentitiesOnly yes
```

Confirm the VPS's own egress IP first (log in and run the echo service there) — that is
the number the target service should later report.

### 1a. Onboarding VPS keys handed over as files

Users send private keys as attachments; they land in
`~/.hermes/cache/documents/` with loose permissions and are pruned, so treat them as
staging, not storage.

```bash
D=~/.hermes/cache/documents
for f in "$D"/doc_*; do chmod 600 "$f"; ssh-keygen -lf "$f"; done   # fingerprint before anything else
```

1. **Fingerprint every incoming key and compare against existing ones first.** A re-sent
   duplicate key produces a second Host block that reads as a new host. `ssh-keygen -lf`
   on all existing keys plus all new ones; identical SHA256 means one entry, not two.
2. `chmod 600` each key *before* touching it with `ssh-keygen`/`ssh` — ssh refuses
   group/world-readable keys with `bad permissions`, which is easy to misread as the key
   being passphrase-protected.
3. Copy the key into the directory ssh actually reads (see the pitfall below), derive the
   public half with `ssh-keygen -y -f <key> > <key>.pub` (644).
4. Add one `Host` block per machine in the existing style (`IdentitiesOnly yes`,
   `StrictHostKeyChecking accept-new`), keeping ports at 22 — non-standard ports are
   transparently interfered with by this host's egress proxy.
5. Verify twice: static resolution with `ssh -G <alias>` (hostname/port/identityfile must
   come from the config, not defaults), then a real
   `ssh -o BatchMode=yes -o ConnectTimeout=15 <alias> 'hostname'` per machine.
6. `shred -u` the source files once the keys are installed, so credentials do not linger
   in the cache dir.

### 1b. Keep the aliases alive across reboots (reconcile script)

`/root/.ssh` is wiped by host reboots while `/home/hatch` persists, so Host blocks and keys
installed once are gone the next morning and `ssh <alias>` fails with no visible cause.

- Write an idempotent reconcile script under `/home/hatch/bin/<fleet>-ssh-reconcile.sh` that
  (a) recreates each `Host` block with the **real IP hard-coded as `HostName`** — a host whose
  name resolves to a fake-ip through the TUN path must never be reached by name,
  (b) points `IdentityFile` at the persisted key under `/home/hatch/.ssh/`, and
  (c) exits 0 printing "nothing to do" when every alias already resolves.
- Invoke it from the watchdog cron the host already runs every minute, not from a second
  scheduler — one scheduler per concern, and the existing one is the one that survives.
- Verify with `ssh -G <alias>` over the whole fleet (hostname/port/identityfile must come from
  the config, not defaults) plus one real
  `ssh -o BatchMode=yes -o ConnectTimeout=15 <alias> hostname` per machine.
- **Do not rehearse the wipe destructively** (moving `/root/.ssh` aside to prove the script
  rebuilds it): the approval layer blocks writes to system state and the prompt times out,
  stalling the session. Idempotence plus the two checks above is the verification.

### 2. Make it mandatory via a wrapper

The wrapper lives in the project (`<project>/env/bin/<tool>`), never in `/usr/local`:

```sh
#!/bin/sh
set -eu
ENV_ROOT="<project>/env"
DRIVER115_PROXY="socks5h://127.0.0.1:<port>"
tunnel_ok() { ss -tln | grep -q '127.0.0.1:<port>' && \
    curl --fail --silent --output /dev/null --connect-timeout 5 --max-time 15 \
         --proxy "$DRIVER115_PROXY" https://<target-domain>/ >/dev/null 2>&1; }
if ! tunnel_ok; then
    ssh -F "$ENV_ROOT/ssh/config" -N -D 127.0.0.1:<port> -o BatchMode=yes \
        -o ExitOnForwardFailure=yes -o ConnectTimeout=15 <alias> >/dev/null 2>&1 &
    echo $! > "$ENV_ROOT/<tool>/.tunnel.pid"
    i=0; while [ $i -lt 15 ]; do sleep 1; i=$((i+1)); \
        tunnel_ok && break; done
    tunnel_ok || { echo "<tool>: proxy unavailable; direct access is disabled" >&2; exit 69; }
fi
unset http_proxy https_proxy all_proxy no_proxy
export HTTP_PROXY="$DRIVER115_PROXY" HTTPS_PROXY="$DRIVER115_PROXY" ALL_PROXY="$DRIVER115_PROXY"
export NO_PROXY="127.0.0.1,localhost"
export <TOOL>_CONFIG="$ENV_ROOT/<tool>/config.toml"
exec "${DRIVER115_REAL_BIN:-$ENV_ROOT/libexec/<tool>-real}" --config "$<TOOL>_CONFIG" "$@"
```

(Adjust the exec line to the real binary's flag set. Batch/variant tools that need a
differently-patched binary go through `DRIVER115_REAL_BIN`.)

### 3. Manage it with systemd, not a shell

Two unit files in `<project>/env/etc/`: one for the daemon, one for the tunnel
(`ExecStart=/usr/bin/ssh -N -D 127.0.0.1:<port> ... <alias>`, `Restart=always`).
Copy to `/etc/systemd/system/`, `systemctl daemon-reload`, `enable --now`.

### 4. Verify end to end

```bash
# egress IP through the tunnel (must equal the VPS's own IP)
curl --socks5-hostname 127.0.0.1:<port> -sS -m 40 https://myip.ipip.net/ | head -1
# control: the same fetch through the sandbox egress (must DIFFER)
curl -sS -m 40 -x http://hatch-egress-proxy:3128 https://myip.ipip.net/ | head -1
# then the real tool through the wrapper
<project>/env/bin/<tool> <authenticated-subcommand>
```

## Host connectivity facts (verify before building any route)

- **`http_proxy`/`https_proxy` are set globally in the shell, and `no_proxy` covers only
  specific addresses — its exact contents differ per process.** The interactive shell on
  this host lists `localhost,127.0.0.1,::1` in `no_proxy`; a cron- or systemd-launched unit
  does not inherit that. A curl to `127.0.0.1:<port>` (a tunnel's own SOCKS port, the mihomo
  controller on 9090, a health endpoint) from an environment without the exception goes
  through the egress proxy and fails with `Empty reply from server` (`curl: (52)`). Read
  `env | grep -i proxy` in the environment you are actually probing instead of assuming
  either way; keep `--noproxy '*'` on every local-port probe, and export
  `no_proxy=127.0.0.1,localhost` for long-lived units — the units are where it costs you.
- **The sandbox DNS returns fake-ip addresses (`198.18.x.x`) for some third-party domains.**
  A `getent hosts <domain>` answer in that range is an assignment by the egress gateway,
  not the target's real address — compare against DoH
  (`https://dns.google/resolve?name=<domain>&type=A`, fetched *through* the egress proxy)
  before concluding a route or a project config is broken.
- **Outbound sockets are blocked unless they go through the egress proxy.** A raw
  `socket.sendto()` to a public DNS or any other host fails with
  `PermissionError: [Errno 1] Operation not permitted`; run network probes through curl or
  the proxy instead.
- **DoH works through the egress proxy.** `curl -x http://hatch-egress-proxy:3128
  'https://dns.google/resolve?...'` returns real answers and is the reliable DNS oracle.
- **The sandbox egress has no single exit IP — it rotates per request.** The same echo
  service fetched repeatedly through the egress proxy returns a different address every
  time, across a wide range inside one provider's block, with IPv4 and IPv6 both rotating.
  Two consecutive fetches disagreeing is normal and is not evidence of a broken route.
  When a target needs one stable address — an IP allowlist, per-IP rate limits, session
  binding — no proxy flag or variant makes the sandbox egress stable; the only answer is a
  pinned route through a user-owned VPS.
- **An echo service's own geo/ASN can describe its CDN, not your exit.** Two echo services
  answering in the same second reported different city/country for the same egress path,
  because one of them is reached through a CDN edge. Use an echo that returns the bare IP
  when location matters, and treat a third-party service's ASN/city as advisory.
- **Explicit `-x http://hatch-egress-proxy:3128` and the ambient env proxy reach the same
  pool.** Sampling both interleaved shows the same rotating range, so switching between
  them changes nothing about egress identity — pick whichever is convenient and prove a
  route by comparing it against a pinned one.
- **A node marked `alive` with a sub-second delay is not proof the traffic left that node.**
  It proves the health-check endpoint was reachable *through the node's dialer*. On a VPS that
  is itself behind NAT the pool cannot be an exit-selection tool at all: every node's traffic
  is SNAT'd to the VPS's own address, so the echo IP is identical whichever node is selected,
  and the node list looks healthy while it is inert. Compare the echo IP before and after a
  switch — unchanged means the pool is not selecting an exit on this host, and no sweep of it
  can then say anything about the target.
- **A geo/legal refusal and an IP-range refusal are different failures with different fixes.**
  `403` with `Sorry, you have been blocked` is a target-side IP decision; `451` with a body
  like `error code: 1026` is the target's own legal/region policy applied to the *exit*, and it
  is answered by changing the exit rather than the node. A different hostname of the same
  service can also carry a different policy — when one domain refuses, try the sibling domain
  on the same reachable exit before reporting the source unavailable.

## Pitfalls

- **A subscription's node list can contain non-nodes.** A base64 subscription decoded to URI
  lines may carry the provider's status text (`剩余流量：…`, `官网：…`) as pseudo-fragments
  that resolve to one shared server, inflating the apparent pool and giving an `url-test`
  group a selectable entry with no usable connection. Keep only entries whose name carries a
  region token, and verify the loaded count against the controller rather than the config.
- **An `url-test` group cannot be driven node-by-node.** It rejects `PUT /proxies/{group}`
  selection, so a per-node sweep needs a temporary `select` group over the same provider —
  remove it after the sweep.
- **`curl --socks5-hostname` `%{remote_ip}` reports the SOCKS endpoint, not the target.**
  With a local tunnel it prints `127.0.0.1` and looks like a broken route. Use the echo
  service, not `remote_ip`, to judge egress.
- **A leftover test process steals the ports and the systemd unit looks healthy.**
  `ss -tlnp` shows a process whose parent is not PID 1 (or whose cwd is a manual launch
  dir) while `systemctl is-active` says `active`; the unit logs `bind: address already in
  use`. Kill the orphan by PID (`kill -TERM <pid>`), never by pattern.
- **`pkill -f`/`pgrep -f` with the pattern text in the same command line matches your own
  shell** and kills it (exit -15). Identify by port with `ss -tlnp`, or write the pattern
  into a `/tmp` script so it is not on the command line.
- **Do not "fix" a geo-block by rewriting the project's proxy config.** If the project's
  own routing (a proxy group, a provider table) does not work on this host, the difference
  is usually the host, not the config. Verify the sandbox's DNS first: a `198.18.x.x`
  answer is a fake-ip assignment, not the target's real address, and no amount of proxy
  config will fix that.
- **A direct connection from this host can be *better* than the tunnel.** Check
  `curl --noproxy '' https://<target>/` before building the tunnel; if it answers, the VPS
  route may be about geo-policy elsewhere and the tunnel is dead weight.
- **`echo $HOME` does not tell you which ssh config is read.** OpenSSH resolves the caller's
  home from the passwd database, so running as root reads `/root/.ssh/config` even when
  `HOME` points elsewhere — a config written to the other directory silently never loads.
  Get the truth from `ssh -v <host> 2>&1 | grep 'Reading configuration'` (first line),
  and install keys plus Host blocks in *that* directory.
- **`ssh -G <alias>` distinguishes "config not read" from "config wrong".** A resolved alias
  echoes its configured hostname/identityfile; an unloaded config echoes the alias itself as
  hostname and a default list of `~/.ssh/id_*` identityfiles. Do not debug config contents
  until this check shows the file was read at all.
- **Fingerprint an incoming key before adding a Host for it.** An already-known key re-sent
  produces a duplicate alias, and the second block looks like a new host while offering no
  new capability. Compare SHA256 fingerprints against every existing key.
- **A key file arriving at 0660 is not a passphrase problem.** Cache-dir attachments are
  group-readable, and ssh refuses them with `UNPROTECTED PRIVATE KEY FILE! ... bad
  permissions`; `ssh-keygen -y -P '' -f` fails the same way. `chmod 600` first, then judge.
- **Delete the source key copies once installed.** Attachments under
  `~/.hermes/cache/documents/` are world-readable staging and get pruned; leaving them is
  a credential leak with no upside. `shred -u` rather than `rm`.
- **Migrated projects must not keep a blanket ambient `ALL_PROXY`**. The sandbox sets
  `HTTP_PROXY` globally; any process that inherits it egresses from the sandbox unless it
  unsets it.
- **An alias-rebuild script on disk is not alias resilience.** A script that exists but is not
  referenced by any watchdog restores nothing — grep the watchdog (and the crontab) for the
  script's path, and confirm the watchdog itself is scheduled, before trusting the fleet.

## See also

`references/project-localization-migration.md` — the recipe for moving a project that ran
on the remote VPS onto this host 1:1 (arch check, sha256 verification, cross-compiling Go
binaries from source, decoupling hardcoded `/usr/local` paths, and the test-suite fallout).

`references/proxy-rotation-and-blocks.md` — triaging a target that refuses this host's IP:
the control-probe interpretation table, the subscription → mihomo node-pool recipe (decode,
region filter, per-protocol fields, `url-test` wiring), the whole-pool sweep script, and when
rotation cannot work.
