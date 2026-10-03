# Localizing hard-coded adapter/surface text

Applies when user-facing wording is duplicated as constants across several
platform adapters (gateway platforms, CLI surfaces, card renderers) and must
become language-dependent **without changing markup or interaction**.

Before designing anything, establish what the user wants preserved. A message
that says "the buttons don't work / the prompt never arrived, now continue"
means: localize the wording, do not restructure the buttons, the callback
values, or the choice set. Those are the interaction contract.

## Why this is not a find-and-replace

Adapter class bodies typically compose markup around a shared English constant
at IMPORT time:

```python
_EA_HEADER = f"⚠️ {EA_HEADER_TEXT}\n\n"      # base adapter
_EA_HEADER = f"⚠️ **{EA_HEADER_TEXT}**\n\n"  # discord override
```

A class attribute therefore cannot see `display.language`: it is evaluated
once, before any user exists. Two consequences:

- Class-level constants must **keep** their English value so import-time markup
  composition still works.
- Localization happens in the **render path, once per prompt**.

## Procedure

1. **Inventory the surfaces and their exact strings.** Grep the shared module
   for the constants, then grep every adapter for its own override of the same
   name. Render each surface once under the ambient language to see what
   actually ships.
2. **Split words from markup.** Put only the words in the catalog; keep `⚠️ `,
   `**`, `<b>`, ` ```bash `, and trailing `": "` separators in the adapter.
3. **Map phrase → key once.** A dict of `{english_phrase: catalog_key}` plus a
   single `str.replace` pass swaps the word and preserves every surrounding
   character, so one edit covers every adapter reusing the same phrasing.
4. **Handle adapters with shorter labels separately.** An adapter whose label
   is not a superstring of the shared English phrase (`"✅ Session"` vs
   `"Allow Session"`) silently no-ops under phrase replacement. Override the
   label builder there and read the word from the catalog per choice, keeping
   the adapter's emoji prefix.
5. **Keep the English branch byte-identical.** Give the formatters a `lang=`
   parameter defaulting to the active language, and assert in tests that the
   English output equals the old constant exactly. This is what keeps existing
   adapter/template tests and untranslated locales green.
6. **Split numbers from units.** A shared English formatter ("5 minutes")
   feeding a translated sentence leaks English into non-English text. Expose
   `{count}` and the unit word separately in the catalog
   (`exec_window_count`, `exec_window_unit_minute` /
   `exec_window_units_minute`) and reassemble per language.
7. **Normalize CJK punctuation inside the adapter's markup.** After the label
   swap, find the first ASCII `:` that *follows the label* and replace it with
   `：`. Do not test `endswith(":")` — markup may sit after the colon
   (`Label:** `), so the string does not end with it.

## Do not translate these

Before claiming a locale is untranslated, diff the values:

- Language-neutral status labels (`FAST`, `NORMAL`, `ON`, `OFF`, `MCP`).
- Catalog values that are pure interpolation (`"• {name} — {preview}"`) — the
  surrounding punctuation is already identical in the target language.
- Input-recognizer strings that must match what a user types (`"o,once"`).
- Internal identifiers that ended up in the user-visible catalog
  (`primary`/`danger` button styles) — move them out, or accept the
  en == zh value.

## Verifying

- Render the **real** surface (the adapter the user actually sees), not just
  the base class, under both the target language and English.
- Assert the interaction contract is untouched: callback/action identifiers
  and the offered choice set must be identical across languages.
- Assert the user's own interpolated content (command text, descriptions) is
  never routed through the translator.
- Assert adapter markup survives (`⚠️`, fences, bold) in every language you
  cover, so a translation cannot silently drop the framing.

## Verifying a localized approval card actually renders

A localized approval prompt cannot be smoke-tested by simply running a risky
command — the approval gate may resolve before a card is ever drawn. Establish
first which decision runs:

- A smart/guardian approval mode auto-approves anything it judges benign, so the
  card never renders and you verify nothing. Either configure the mode that
  requires a human decision, or point the operator policy at the fixture.
- The gate's effective mode is the reader's default, not a commented-out config
  line; a commented `mode:` means the default is in force.

Then drive the real render path: create a throwaway fixture, delete the fixture,
then delete real data only if the user asks. Build the fixture yourself
(`mkdir -p <tmp>/fixture/nested`, write placeholder files, record `du -sh`)
so the destructive command operates on known-safe bytes, and confirm the target
exists before running `rm -rf` on it. Test the high-risk and low-risk branches
separately: the offered choice set differs (a smart-deny or no-session case
reduces to once/deny), and the routing identifiers must be identical in both.

## Catalog parity

Adding a key to the baseline catalog requires the same key in every other
catalog file in the same change, or runtime falls back to English for those
users. Write the block for the target language and carry English placeholders
for locales you have not translated; scope translation claims to the locales
you actually reviewed.
