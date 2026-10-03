# RED validity: making a failing test fail for the right reason

A RED only counts when the test ran and the code under test behaved wrongly. These recipes turn an unusable RED (compile error, import error, immediate pass) into a real one **without** implementing production logic.

This is the single most expensive failure mode in strict-TDD feature work: the run looks like a failure, so the next step looks legitimate, but nothing about behavior was proven.

## Rule

Before writing production code, confirm all three:

1. The failure is an **assertion** failure — the test compiled, imported, ran the code under test, and the code behaved wrongly. A build error, unresolved import, or "undefined symbol" is **not** a RED.
2. The failure message is the expected one, for the expected reason.
3. The wrong behavior is exactly the behavior about to be implemented.

If any fails, scaffold below and re-run. Never implement real logic to get past an import error.

## Recipe: missing module / unresolved import

Symptom: `Failed to resolve import "./foo"`, `cannot find module`, `unknown field Source in struct literal of type X`.

Cause: the test names a symbol that does not exist yet, so the suite cannot even load it.

Fix: create the module (or add the field to the struct) with a **deliberately wrong** body — empty strings, `nil`, a struct of zero values — so the test compiles and the assertions fail.

```go
// deliberately wrong: zeros are not what the test expects
type Thing struct{ Approved bool }
func Evaluate() Thing { return Thing{} }
```

```ts
// deliberately wrong: placeholders that fail the assertions
export function buildSummary(): Summary {
  return { traderId: '', modelId: '', coinPool: [], isRunning: true }
}
```

Write the real implementation in GREEN. Note the wrong stub in the commit only if it ships; otherwise delete it.

## Recipe: missing symbol the test references

Symptom: `undefined: myField`, `no field or method X on type Y`.

Fix: add the minimal production scaffold (struct field, method signature, exported wrapper) and nothing else. Do not fill defaults that would change behavior — e.g. adding a `marginMode` field must default to the safe value, not to whatever makes the test pass.

## Recipe: the test passes immediately

Symptom: `--- PASS` on the first run of a test written before the feature.

This is not a GREEN. The test is not exercising the path you think:

- **An earlier guard returned first.** A network call, nil check, or validation branch aborted the path and returned an error, and the assertion only checked `err != nil`. A mock embedding a nil interface can also make an unoverridden method unreachable. Assert on the *specific* error and on the absence of the side effect (`calls == 0`).
- **A mock absorbed the path.** Determine which branch actually ran before believing the pass; record the counter values.
- **The assertion is over-broad.** `expect(x).toBeTruthy()` passes on almost anything; assert the exact value.

Instrument side-effect counters on the mock (call counts, recorded arguments, recorded request bodies) so the reason for any pass or fail is visible in the output.

## Recipe: no injection point for a package-level dependency

Symptom: the code under test calls `pkg.Fetch(...)` directly, so the test would need the live network.

Fix: add an indirection and keep the production default identical.

```go
// production keeps calling the real function
var LoadThing = Fetch
...
data, err := LoadThing(symbol)   // call site uses the var
```

```ts
export const loadThing = fetchThing
```

The test restores the original in cleanup. This is a testability seam, not a behavior change — do not describe it as new behavior in the commit.

## Recipe: fake HTTP responses in Go tests

`io.ReadAll` and `http.Client` require `io.EOF`, not an error that formats as "EOF".

```go
func (b *body) Read(p []byte) (int, error) {
	if b.pos >= len(b.data) { return 0, io.EOF }   // NOT fmt.Errorf("EOF")
	...
}
```

A formatted error makes every request fail with a misleading `failed to read response: EOF` that looks like a bug in the code under test.

## Recipe: short variable declaration collisions in Go

Adding `qty, err := ...` to a function that already declares `err` later with `:=` fails the build with `no new variables on left side of :=`. Use `=` from the second declaration onward, or move the declaration.

A compile failure during GREEN means the RED was never re-established: revert and re-run the test first. If you already applied production code before watching the RED, revert it, capture the real failing run, then re-apply — committing without a recorded RED leaves the test unvalidated.

## Recipe: verifying refactors against mocks and seams

- Static types on a mock's fields do not make the production path use them; check which branch actually executes.
- Record the RED to a log with the exact command, raw output, and exit code next to the GREEN log. A suite only ever seen passing has never been validated.

## Recording evidence

Capture the RED run with the exact command, raw output, and exit code, and keep it beside the GREEN log. The RED log is the only proof the test *can* fail.
