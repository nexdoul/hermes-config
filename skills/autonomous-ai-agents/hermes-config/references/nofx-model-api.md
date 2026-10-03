# NOFX model configuration through its API

Use when connecting an existing OpenAI-compatible provider to NOFX. Read the deployed handlers first: repository docs and current UI can diverge, and a supported-provider selector may expose fewer choices than the backend accepts.

## Procedure

1. Obtain an authorized application session through normal login or an explicitly supported administrative API. Never derive a login token from a server JWT signing secret. Keep credentials out of tool output.
2. Read `GET /api/models` and the trader list. Record existing model IDs and active consumers. Do not overwrite a Claw402 wallet model with a normal API key: that field has provider-specific meaning. Do not change active traders as a side effect of model setup.
3. Inspect `api/handler_ai_model.go`, `store/ai_model.go`, and the actual provider client for payload shape, provider inference, key preservation, and supported protocol. Some versions infer the provider from the final underscore-delimited ID component; an OpenAI-compatible record therefore needs an ID ending in `_openai`.
4. Verify the exact canonical model using the existing relay's Chat Completions endpoint. Preserve required provider headers, including User-Agent when applicable; default Python HTTP headers can be rejected even when a browser-like request succeeds. A successful harmless completion proves the relay, not NOFX's decision parsing.
5. Save through `PUT /api/models` with explicit values:

```json
{
  "models": {
    "<user-owned-model-id-ending-in-_openai>": {
      "enabled": true,
      "api_key": "<resolved-in-memory>",
      "custom_api_url": "https://provider.example/v1",
      "custom_model_name": "<canonical-model-id>"
    }
  }
}
```

Use a base URL without `/chat/completions` unless the deployed client explicitly supports full-path overrides. Preserve unrelated model records. An empty API key can mean 'retain existing credential', not 'clear it'; check the handler before resetting credentials.

6. If transport encryption is enabled, use the application's encryption interface described below rather than disabling it or writing plaintext directly to SQLite.
7. Read `GET /api/models` again and assert exact ID, `provider`, `enabled`, `has_api_key`, `customApiUrl`, and `customModelName`. Inspect storage only through nonsecret checks if needed. The application's encrypted-string type encrypts on save; direct SQL bypasses that behavior and runtime reload hooks.
8. If a nontrading application-native model test is available, run it. Otherwise report precisely 'relay tested and configuration read back; application inference/decision execution not exercised'. Never start trading to prove model setup.

## Encrypted transport recipe

Confirm endpoint names and enabled state against the deployed server. The inspected implementation exposes `GET /api/crypto/config` and `GET /api/crypto/public-key`.

- Generate a random 32-byte AES key and 12-byte IV.
- Encrypt the JSON payload with AES-GCM; append the authentication tag as the library normally returns it.
- Wrap the AES key using the server public key with RSA-OAEP, SHA-256 for both OAEP and MGF1, and no label.
- Encode `wrappedKey`, `iv`, and `ciphertext` as unpadded URL-safe base64.
- Include `ts` as current Unix seconds. The server checks freshness; recreate the payload immediately before submission rather than reusing ciphertext.
- If using AAD, pass the identical bytes to AES-GCM and send them as URL-safe base64 in `aad`; otherwise omit it.
- Submit the encrypted object to the same authenticated model-update endpoint.

## Reading community guidance

Treat community reports as diagnostic hypotheses, not established behavior of the user's deployment. Confirm actual UI/version before promising custom prompts, backtesting, simulation, or a particular exchange mode. For small trading budgets, distinguish connectivity and order-lifecycle tests from evidence of profitability; model fees and trading capital are separate budgets. Stopping the automation must not be represented as closing existing exchange positions unless verified.
