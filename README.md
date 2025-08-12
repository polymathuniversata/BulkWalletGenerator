# Telegram Wallet Generator (Local, Lightweight)

Generates 12-word BIP39 mnemonics and derives multichain wallet addresses via a Telegram bot. Runs locally, minimal dependencies.

Supported chains:
- Ethereum (ETH, EVM) — `m/44'/60'/0'/0/0`
- BASE (EVM) — `m/44'/60'/0'/0/0`
- BSC (EVM) — `m/44'/60'/0'/0/0`
- Polygon (EVM) — `m/44'/60'/0'/0/0`
- Avalanche C-Chain (AVAXC, EVM) — `m/44'/60'/0'/0/0`
- Bitcoin (BTC, Bech32) — `m/84'/0'/0'/0/0` (bc1...)
- Litecoin (LTC, Bech32) — `m/84'/2'/0'/0/0` (ltc1...)
- Dogecoin (DOGE) — `m/44'/3'/0'/0/0` (D...)
- Tron (TRX) — `m/44'/195'/0'/0/0` (T...)
- XRP (Ripple) — `m/44'/144'/0'/0/0` (r...)
- Solana (SOL) — `m/44'/501'/0'/0'` (Base58 pubkey)
- TON (The Open Network) — `m/44'/607'/0'/0/0`

Security:
- Mnemonics/keys generated in-memory only.
- No persistence; no logging of sensitive material.
- One-time seed reveal with auto-delete.
- Basic per-user rate limiting.
 - Optional local profile stores only non-sensitive data (addresses + derivation paths) per user.

## Quickstart

1) Create and activate a Python 3.10+ venv

```
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
```

2) Install dependencies

```
pip install -r requirements.txt
```

3) Configure

```
cp .env.example .env
# put your Telegram bot token in TELEGRAM_BOT_TOKEN
```

4) Run

```
python -m src.bot
```

## Commands
- /start, /help — usage info
- /chains — list supported chains
- /generate [CHAIN] — generate mnemonic and address for a chain
  - CHAIN ∈ {ETH, BTC, SOL, BASE, BSC, POLYGON, AVAXC, TRON, XRP, DOGE, LTC, TON}
  - Example: `/generate TON`
 - /bulk <CHAIN> <COUNT 1-20> — generate multiple wallets and download CSV
 - /bal <EVM_CHAIN> <ADDR1> [ADDR2 ...] — bulk balance check for EVM chains (ETH, BASE, BSC, POLYGON, AVAXC); returns CSV
 - /my [CHAIN] — show your saved profile wallets (optionally filter by chain)
 - /mycsv — export your saved profile wallets to CSV
  - /mybal <CHAIN> — balances for your saved addresses
    - EVM: ETH, BASE, BSC, POLYGON, AVAXC (requires RPC envs)
    - Non‑EVM (opt‑in): BTC, SOL, TON (requires enabling env flags)
  - /clearprofile — delete your saved profile wallets (addresses only)
 - /bulkzip <CHAIN> <COUNT> — mass-generate wallets to chunked CSVs and ZIP them for download (contains mnemonics)
 - /jobs — list your active bulk ZIP jobs (admins see all)
 - /pause <JOB_ID> — pause a bulk ZIP job
 - /resume <JOB_ID> — resume a paused job
 - /cancel <JOB_ID> — cancel a running job
 - /version — show supported chains and which EVM RPCs are configured

## Notes
- Add your bot in Telegram via BotFather and obtain the token.
- Keep your seed secure. Do not forward, screenshot, or cloud-sync.
- For Solana, public key is Base58.
 - Reply keyboard includes: Generate Wallet, Chains, Show Seed, Help, Bulk Help, Bulk ZIP, My Profile, My CSV.
 - Bulk ZIP CSVs include mnemonics for backup. Store and transfer securely.

## Environment (balances & persistence)
To enable `/bal` and `/mybal` EVM balance checks, set RPC endpoints in `.env`:

```
RPC_ETH=
RPC_BASE=
RPC_BSC=
RPC_POLYGON=
RPC_AVAXC=
```

Use your own provider URLs (e.g., Infura, Alchemy, Ankr, QuickNode). Public endpoints may be rate-limited.

Additional environment variables:

```
# Optional data directory for local DB (profiles.db)
DATA_DIR=.

# Admin users (Telegram numeric user IDs) to allow higher bulk limits
ADMIN_USER_IDS=

# Bulk ZIP generation caps (safety)
BULKZIP_CSV_CHUNK=10000
BULKZIP_ZIP_CSVS=10
BULKZIP_MAX_NONADMIN=100000
BULKZIP_MAX_COUNT=1000000

# Optional non‑EVM balance support (opt‑in)
# BTC via Blockstream API (or compatible)
ENABLE_BTC_BAL=0
BTC_API_BASE=https://blockstream.info/api

# Solana via JSON-RPC
ENABLE_SOL_BAL=0
SOL_RPC_URL=

# TON via toncenter-compatible API
ENABLE_TON_BAL=0
TON_API_BASE=
TON_API_KEY=
```

Behavior:
- A local SQLite DB `profiles.db` is created in `DATA_DIR` to store per-user profile addresses and paths.
- Admins (listed in ADMIN_USER_IDS) can run bigger `/bulkzip` counts up to BULKZIP_MAX_COUNT; others up to BULKZIP_MAX_NONADMIN.
- Bulk job metadata is persisted to `DATA_DIR/jobs.json`. On restart, any previously running/paused jobs are shown as `failed` in `/jobs` for clarity.

## Docs
See the docs/ directory:
- docs/index.md
- docs/architecture.md
- docs/setup.md
- docs/chains.md
- docs/usage.md

## Development (auto-reload)
Use the watchdog runner to automatically restart the bot on file changes during development:

```powershell
pip install -r requirements.txt
python run_dev.py
```

## Roadmap
- Encrypted keystore export (optional)
- Optional Dockerfile
- Testnet toggles
