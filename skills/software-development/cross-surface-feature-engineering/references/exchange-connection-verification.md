# Exchange connection verification

Use when configuring or checking trading-app exchange credentials, especially when a user asks whether a saved connection is ready to use.

## Verification sequence

1. Inspect the application's exchange-account state endpoint, probe implementation, and the adapter constructor before calling it. Trace initialization through to transport methods: an account GET can still POST position-mode changes during construction. Prove constructors issue no writes and account probes use only reads before describing a check as read-only; do not use trader start, launch preflight with force flags, or real orders as connection tests.
2. Resolve the saved exchange identity, enabled state, main/subaccount ownership, and real/test environment without printing credentials or account identifiers unnecessarily. For three-part HMAC credentials, map API Key, Secret Key, and user-chosen API Passphrase explicitly; the passphrase is not the login password.
3. Query the authenticated state endpoint through the application's existing authorized access. NOFX exposes `GET /api/exchanges/account-state`; read each entry's `status`, `display_balance`, `asset`, `checked_at`, and any error fields. A `status: ok` balance response verifies the read path, not permission to place orders or the correctness of exchange-side protection.
4. Identify which balance/product the adapter reads from its `GetBalance` implementation. If it returns zero, ask where the user's funds sit before recommending transfers: spot/funding versus futures, main versus subaccount, USDT versus USDC, and classic versus unified account mode can differ. Label an unverified product inference rather than asserting it as fact.
5. If the user confirms funds are in spot while the adapter queries futures, explain manual transfer into the matching account/product. Do not advise another deposit or larger leverage to overcome an empty balance. A transfer does not itself open a position, but makes funds available to a trading-enabled bot. Leave transfer amount and execution with the user unless explicitly authorized.
6. Re-query after the user reports completion. Only after the correct funded balance appears should the next step be preparing a constrained strategy and a stopped trader. Starting autonomous trading requires its own explicit authorization and risk checks.

## End-to-end route adaptation

1. Separate execution venue, analysis-market provenance, signal provider, and model billing in the behavior matrix. Public market data from an exchange does not require wallet authorization; using a different venue's reference candles is not native execution-venue data. Display actual provenance and disclose fallbacks rather than changing labels.
2. Test configuration round-trips before exposing launch controls. Seed different major/altcoin leverage, low position limits, enabled indicators, exclusions, and prompts; opening, listing, saving without edits, and preparing launch must preserve them. Inspect default-template provisioning and name-based migrations because list GETs can silently rewrite risk or delete user records.
3. Bind model, exchange account, and strategy by explicitly selected owned IDs. Create a stopped trader, keep optional wallet onboarding out of the mandatory route, and separate save, analysis, and start; automatic first-record or name-based selection can launch the wrong configuration.
4. Audit paid-data fallback outside the UI. A self-hosted model may still inherit a different model's payment wallet, and the decision engine may request optional rankings unconditionally. Mock transports and assert zero paid calls across preview, analysis, page mount, focus, and polling when paid features are off.
5. Design no-trade analysis with read-only account and market dependencies and the production decision parser, not an executable trader instance. Identify hypothetical balances explicitly; a prompt assembled with a sample balance is not actual-account readiness. Assert no order capability, no account-mode writes, unchanged running status, and an explicit unexecuted result. Obtain separate approval for a real model call's cost.
6. Prove execution prerequisites with mocks before offering live startup. Account-mode errors must stop before opening, quantity-format errors must stop protection requests, and failed mandatory protection must expose the existing compensation result rather than report success. Check persisted running flags before backend replacement because restart-time auto-resume can trade without a fresh UI click.

## Report shape

Use a short table separating **credentials/read connection**, **queried balance**, **environment**, and **running traders**. State that order permissions, fills, and stop-loss execution remain untested when no orders were placed. Give the single next blocking step rather than calling the integration fully ready.

## Payment-route distinction

Explain separately the model-call budget and trading collateral. A configured external OpenAI-compatible API consumes that provider key's quota; it does not require funding a wallet-based AI provider merely because the application's generic onboarding promotes that route. A Hyperliquid authorization widget is optional for a Bitget/OKX connection, not a general-purpose account connector. Preserve optional integrations when hiding promotional onboarding; do not equate not needed for this route with globally useless.
