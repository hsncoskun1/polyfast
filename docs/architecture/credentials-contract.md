# Credentials Contract

## Three-Layer Model

| Layer | Purpose | Contains | Accessible By |
|---|---|---|---|
| **Masked display** | Show credential status in UI | Last 4 chars + masked prefix (`****a1b2`) | Frontend |
| **Secure storage** | Persist credentials at rest | Encrypted values in backend keystore | Backend only |
| **Metadata only** | Inform frontend of credential state | Field name, bound status, last-updated timestamp | Frontend |

The frontend never receives, stores, or transmits actual credential values. It only receives metadata and masked display strings.

## Credential Fields

| Field | Purpose | Format |
|---|---|---|
| `api_key` | Polymarket API authentication | Alphanumeric string |
| `api_secret` | Polymarket API request signing | Base64-encoded secret |
| `api_passphrase` | Polymarket API passphrase | User-defined string |
| `private_key` | Wallet signing key for on-chain ops | Hex-encoded 32-byte key |
| `funder_address` | USDC funding wallet address | `0x`-prefixed Ethereum address |
| `relayer_key` | Relayer API authentication | Alphanumeric token |

## Propagation Rules

1. Credentials are entered via a dedicated backend endpoint, never through the frontend.
2. On receipt, backend encrypts and stores immediately; plaintext is discarded from memory.
3. Backend pushes only metadata (bound/unbound, masked value) to frontend.
4. Credential values are never included in API responses, WebSocket messages, or logs.

## Rebind Rules

- Any credential can be rebound by submitting a new value to the backend endpoint.
- Rebinding invalidates the previous value immediately.
- Active sessions using the old credential are terminated and must re-authenticate.
- Rebind events are logged (timestamp + field name only, never the value).

## Absolute Prohibitions

- **No plaintext credentials in logs** -- not in application logs, debug output, error messages, or crash dumps.
- **No credentials in frontend state** -- not in Redux, localStorage, sessionStorage, cookies, or DOM.
- **No credentials in URLs** -- not as query parameters, path segments, or fragment identifiers.
- **No credentials in source control** -- `.env` files are `.gitignore`-listed; secrets use environment variables or encrypted keystore.
