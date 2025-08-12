# Telegram Wallet Generator Plan

## Goal
Build a lightweight, locally-run Telegram bot that generates 12-word BIP39 mnemonics and derives multichain wallet addresses.

## Scope (MVP)
- 12-word mnemonic (BIP39, 128-bit entropy).
- Chains: Ethereum (EVM), Bitcoin (Bech32), Solana.
- No persistence; generate in-memory only.
- Return: address, derivation path, QR for address, one-time seed reveal with delete.
- Commands: /start, /help, /chains, /generate [CHAIN]
- Local run via Python, minimal dependencies.

## Tech Stack
- Python 3.10+
- aiogram (Telegram bot framework)
- bip-utils (BIP39/BIP32/BIP44 derivations, multi-chain support)
- qrcode (for QR images)
- python-dotenv (env config)

## Security
- Do not log mnemonics/private keys.
- Send seed only on explicit user request; auto-delete after a short delay.
- Optional "Delete now" button to immediately purge the seed message.
- Rate-limit wallet generation per user to mitigate abuse.

## Tasks
- [x] Define requirements
- [x] Scaffold project (files, structure)
- [x] Implement wallet derivation per chain (multi-chain: ETH, BTC, SOL, BASE, BSC, POLYGON, AVAXC, TRON, XRP, DOGE, LTC, TON)
- [x] Implement Telegram bot commands (generate, seed reveal, bulk, balances, profiles)
- [x] Add ephemeral seed reveal + auto-delete
- [x] Add rate limiting
- [x] Test locally (manual)

## Current Work
- [ ] Synchronize .env.example with all variables (admins, DATA_DIR, RPCs, non‑EVM flags, bulk limits)
- [ ] Update architecture docs to reflect persistence (profiles.db, jobs.json), balances, bulk ZIP/jobs
- [ ] Unify dev entrypoint (prefer run_dev.py; remove integrated watcher)
- [ ] Refactor bot into modules (handlers, balances, store, jobs, ui) for maintainability
- [ ] Add tests (derivation paths, rate limit, seed TTL, balance clients)
- [ ] Optional: encrypted CSV export for seeds in bulk flows

## Future
- Add TON
- Add export encrypted keystore
- Dockerfile (optional)
- Testnet/mainnet toggles per chain
