# Architecture

- App type: Telegram bot (aiogram v3)
- Language: Python 3.10+
- Local-first, minimal deps

## Modules
- `src/wallets.py`
  - BIP39 mnemonic generation (12 words)
  - Per-chain derivation helpers
  - `generate_wallet(chain)` returns `WalletInfo` with `address`, `derivation_path`, `mnemonic`
  - `address_qr_png(address)` returns in-memory PNG
- `src/bot.py` (Enhanced UI/UX - August 2025)
  - Bot bootstrap with modern interface design
  - Enhanced interactive menu with icons and logical grouping
  - Contextual help system with topic-based assistance
  - Progressive disclosure for complex operations
  - Smart chain selection with blockchain categorization
  - Rate limiting with user-friendly messaging
  - Interactive seed reveal with enhanced security warnings
  - Profile persistence with portfolio-style presentation
  - Advanced bulk operations with job management UI
  - Commands: All legacy commands + enhanced UI callbacks
  - Config via `.env` with validation

## Enhanced User Flows (Updated August 2025)

### **Primary Generation Flow**
1. User opens bot → Enhanced welcome with `/start`
2. User taps "🔑 Quick Generate" → Smart chain selection with icons
3. Bot calls `generate_wallet(chain)` with rate limiting
4. Bot sends address + derivation path + QR with enhanced formatting
5. Interactive seed reveal with "🔑 Show Seed Phrase" button
6. Auto-save to profile + success confirmation with next action options

### **Portfolio Management Flow**
1. User taps "💰 My Wallets" → Enhanced summary with wallet counts
2. Options: View by Chain, Export CSV, Check Balances, Clear All
3. Chain-specific views with formatted address display
4. Integrated balance checking with visual indicators

### **Bulk Operations Flow** 
1. User taps "🔄 Bulk Operations" → CSV/ZIP selection
2. Progressive count input with validation
3. Enhanced chain selection with categorization
4. Job progress tracking with pause/resume/cancel controls
5. Secure file delivery with safety warnings

## Security
- Mnemonics/private keys: never logged; held only in memory with short TTL
- Persistent data: only addresses, derivation paths, and timestamps in `profiles.db`; bulk job metadata in `DATA_DIR/jobs.json`
- Basic per-user rate limiting for generation endpoints
- Bulk CSV and Bulk ZIP contain mnemonics by design; users are warned to store offline and securely

## Balances
- EVM: JSON-RPC (`eth_getBalance`) using env-configured endpoints per chain (ETH, BASE, BSC, POLYGON, AVAXC)
- BTC (optional): Blockstream-compatible REST API
- SOL (optional): Solana JSON-RPC `getBalance`
- TON (optional): toncenter-compatible API
All non‑EVM balances are disabled by default and gated by env flags.

## Persistence
- `profiles.db` (SQLite) at `DATA_DIR` (default `.`) stores non-sensitive profile wallets per user
- `jobs.json` at `DATA_DIR` holds bulk ZIP job metadata for `/jobs` visibility across restarts

## Development
- Preferred dev runner: `run_dev.py` (watchdog-based autoreload)
- Production/local run: `python -m src.bot`
- **Current Architecture**: Monolithic (1600+ lines) - refactoring planned
- **UI Framework**: Enhanced aiogram v3 with modern interactive elements
- **Future Structure**: Planned modularization into handlers/, services/, ui/ modules
