# M6-2 – Token Client (ensure_token → REST)

## Purpose
Connect authentication to real REST calls while keeping the rest of the system pure.

## Modules
- `libs/token_cache.py`
  - file-based token cache (`TokenRecord`)
- `libs/kiwoom_token_client.py`
  - `ensure_token()` loads cache, refreshes if needed, saves cache
  - `auth_headers()` provides `Authorization: Bearer <token>`

## Notes
- Token endpoint is set to `/oauth2/token` by default.
  - If Kiwoom spec differs, override in the client (or later add env key).
- Use MOCK mode first.
- This is still isolated: only auth is wired, no trading logic.
