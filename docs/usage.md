# Usage

## Telegram
- Start chat with your bot.
- Send `/start` or `/menu` to open the menu.
- Tap `Generate Wallet` → choose a chain.
- Bot replies with the address, derivation path, and a QR image.
- Tap `Show Seed` (or `/showseed`) to reveal your 12-word seed once. It will auto-delete in ~30 seconds.
- Use `/delete` by replying to any message you want removed.

Reply keyboard buttons:
- Generate Wallet, Chains, Show Seed, Help
- Bulk Help, Bulk ZIP
- My Profile, My CSV

## Commands
- `/start` — welcome message + menu
- `/menu` — show menu
- `/chains` — list supported chains
- `/generate <CHAIN>` — generate wallet for a chain
- `/showseed` — one-time seed reveal
- `/delete` — delete the replied-to message
 - `/my [CHAIN]` — show your saved profile wallets (addresses + derivation paths)
 - `/mycsv` — export your profile wallets to CSV
 - `/mybal <CHAIN>` — balances for your saved addresses
   - EVM: ETH, BASE, BSC, POLYGON, AVAXC (requires RPC envs)
   - Non‑EVM (opt‑in): BTC, SOL, TON (requires enabling env flags)
 - `/clearprofile` — delete all your saved profile wallets (non-sensitive)
 - `/bulk <CHAIN> <COUNT 1-20>` — small batch CSV export
 - `/bulkzip <CHAIN> <COUNT>` — massive generation, chunked CSVs zipped for download
 - `/jobs` — list active bulk ZIP jobs (admins see all)
 - `/pause <JOB_ID>` — pause a bulk ZIP job
 - `/resume <JOB_ID>` — resume a paused job
 - `/cancel <JOB_ID>` — cancel a running job

## Notes
- If a button doesn’t respond, retry or use the slash-command.
- Seeds expire in memory after 3 minutes.
- Rate limit is applied per user per minute.
 - Profile data is local-only and stores no mnemonics/private keys.

### Balance support notes
- EVM balances require RPC endpoints set in your `.env` (`RPC_ETH`, `RPC_BASE`, etc.).
- Non‑EVM balances are disabled by default. Enable via:
  - `ENABLE_BTC_BAL=1` and optionally `BTC_API_BASE`
  - `ENABLE_SOL_BAL=1` and `SOL_RPC_URL`
  - `ENABLE_TON_BAL=1` and `TON_API_BASE` (+ optional `TON_API_KEY`)

### Bulk job persistence
- Bulk job metadata is saved to `DATA_DIR/jobs.json` so `/jobs` can reflect prior runs after a restart.
- Any in-flight (running/paused) jobs from a previous process are marked `failed` on startup to avoid confusion.
