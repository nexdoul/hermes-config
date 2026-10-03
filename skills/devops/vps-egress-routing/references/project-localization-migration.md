# Migrating a VPS-run project onto this host, 1:1

Procedure for taking a project that ran on a remote VPS and making it run identically on
htch-runtime. Most of the pain is not the files — it is architecture and absolute paths.

## Pre-flight

1. **Ask the user what is in scope.** Migrating a monolith is usually wrong; the ask is
   often "just this component". Confirm which components survive before packing anything.
2. **Check the architecture before anything else.**
   `uname -m` locally vs `uname -m` on the VPS. An `aarch64` VPS cannot run its binaries on
   an `x86_64` host unless they are statically linked. Decide per binary: static (copy as-is),
   source available (compile), or dropped.
3. **Locate the real project directory.** Do not trust a remembered path —
   `ssh <vps> 'ls <suspect> && du -sh <suspect>'` first. Nested subdirectories are common
   and packing the wrong root wastes a transfer.

## Transfer

```bash
# on the VPS
tar --exclude=__pycache__ --exclude='*.pyc' -czf /tmp/proj.tar.gz <dir>
# from this host
export no_proxy='<vps-ip>' NO_PROXY='<vps-ip>'
scp -i ~/.ssh/<key> root@<vps-ip>:/tmp/proj.tar.gz /tmp/
```

Verify integrity by aggregating, not by eye:

```bash
ssh <vps> 'cd <dir> && find . -type f ! -name "*.pyc" -exec sha256sum {} + | sort | sha256sum'
cd /local/dir && find . -type f ! -name '*.pyc' -exec sha256sum {} + | sort | sha256sum
```

(`__pycache__`/`.pyc` legitimately differ; filter them on both sides.)

## Flat layout, unless the user asks otherwise

- Put all project files directly in `<project>/` — no `project/tarball/`, no
  `project/project/`. The user rejects "叠这么多层".
- Keep environment material in a self-contained `env/` subdirectory: `bin/` (wrappers),
  `libexec/` (real binaries), `etc/` (unit files), `ssh/`, plus any per-tool config.
- **Nothing under `/home/hatch` needs a self-heal/keepalive sync agent.** It survives
  rebuilds. Building one is redundant work the user will reject.

## Cross-compiling a Go binary from source

1. Get a current toolchain. The pinned upstream version may be EOL; read the real list
   instead of guessing:
   `curl -sS --noproxy '*' 'https://go.dev/dl/?mode=json'`
2. Install it inside the project (`env/go`), not system-wide, so the project stays portable.
3. `git fetch --depth 1 origin tag <TAG> && git checkout <TAG>` — version pins matter, and
   the project's patch files apply only to their tag. `git apply --check` first.
4. Set `GOPROXY=https://goproxy.cn,direct` for this host.
5. If the project ships a build script that ends in
   `install -m 0755 ... /usr/local/...`, retarget only the install destination; keep the
   clone/apply/build steps intact.
6. Stamp the version: `go build -trimpath -ldflags="-s -w -X main.version=<TAG>"`.
7. Keep the wrapper layer (see the parent skill) between the caller and the real binary.

## Decoupling hardcoded paths

Source that hardcodes `/usr/local/bin/<tool>` breaks on the new host. Do three things:

1. Add a resolver in the module and use it everywhere:
   ```python
   def _find_env_root() -> Path:
       override = os.environ.get("JAVDB_ENV_ROOT")
       if override: return Path(override)
       for parent in Path(__file__).resolve().parents:
           if (parent / "env" / "bin" / "<tool>").is_file(): return parent / "env"
       return Path("/usr/local")   # keeps the VPS layout working
   ```
2. **Preserve the safety check, not the path.** The guard usually exists to forbid calling
   the raw binary ("must use the wrapper"). When you relocate, reimplement it as a content
   test on the wrapper file, or the guard silently stops checking anything.
3. Change argparse defaults from the absolute path to `None` and let the constructor
   resolve — the same code then serves both hosts.

## Test-suite fallout

- **A hardcoded remote path in a test is a localization bug, not a failing test.** Replace
  the literal with a module-level constant derived from the resolver
  (`WRAPPER = _cs._default_wrapper_path()`), leaving every assertion untouched.
- **Beware a stale copy of the same module at the project root.** If the root has an old
  `foo.py` and the package has the current `foo.py`, running pytest from the root imports
  the wrong one and reports missing symbols. Run pytest from the package directory and set
  `PYTHONPATH` to the package and its internal lib.
- **Entry-point `required` checks that list `/usr/local/bin/<tool>` will return
  ENVIRONMENT_NOT_READY (exit 69) before any real work.** Resolve those entries through the
  same constructor the tests use.
- Expect some tests to be **environment-coupled by design** (mock the route, assert exit
  codes). Keep the exit-code contract; only change what the environment check looks at.

## Verifying you reached 1:1

- The migrated tool answers an authenticated subcommand with the same account identity as
  the VPS (user ID / username / plan status) — not merely "it runs".
- Diff the VPS's config against the migrated copy: the only acceptable differences are
  relative-path rewrites and an explicitly-commented environment adaptation. Anything else
  is a silent behaviour change.
- Full test suite green on this host, run from the package directory with the tool on PATH.
