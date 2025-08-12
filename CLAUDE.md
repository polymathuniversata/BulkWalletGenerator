# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Telegram Wallet Generator** bot - a local, lightweight Python application that generates BIP39 12-word mnemonics and derives multi-chain wallet addresses through an enhanced Telegram bot interface. The bot emphasizes security by generating keys in-memory only with no persistence of sensitive data.

**Recent Major Update**: Complete UI/UX overhaul with modern icon-based interface, contextual help system, and streamlined user workflows for improved accessibility and user experience.

**Core functionality:**
- Generate BIP39 12-word mnemonics for 12 supported blockchain networks
- Derive wallet addresses using standard BIP44/BIP84 derivation paths
- Provide QR codes for addresses
- Ephemeral seed phrase reveal (3-minute TTL with auto-delete)
- Bulk wallet generation with CSV/ZIP export
- Balance checking for supported chains
- User profile management (non-sensitive address storage)

**Supported chains:** ETH, BTC, SOL, BASE, BSC, POLYGON, AVAXC, TRON, XRP, DOGE, LTC, TON

**UI/UX Features:**
- Icon-based menu with clear visual hierarchy (🔑 Quick Generate, 💰 My Wallets, etc.)
- Smart chain selection organized by blockchain type
- Contextual help system with FAQ and setup guides
- Progressive disclosure for complex bulk operations
- Enhanced confirmation flows for destructive actions

**Security & Reliability Features (August 2025 Update):**
- Comprehensive input validation with `src/validators.py`
- Robust async error handling with automatic retry logic
- Rate limiting with user-friendly feedback
- XSS and injection attack prevention
- Extensive test coverage (150+ tests) for reliability

## Commands for Development

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
./venv/Scripts/activate  # Windows PowerShell: venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env to set TELEGRAM_BOT_TOKEN
```

### Running the Bot
```bash
# Development mode (with auto-reload on file changes)
python run_dev.py

# Production/manual mode
python -m src.bot
```

### Testing (Enhanced Test Suite)
```bash
# Run comprehensive test suite
python run_tests.py

# Run quick validation tests
python run_tests.py --quick

# Run tests with coverage reporting
python run_tests.py --coverage

# Run specific test categories
pytest tests/test_validators.py -v    # Input validation tests
pytest tests/test_error_handling.py -v  # Error handling tests
pytest tests/test_ui_flows.py -v     # UI interaction tests
pytest tests/test_integration.py -v  # End-to-end integration tests
```

## Architecture

**Core modules:**
- `src/wallets.py`: BIP39 mnemonic generation, multi-chain derivation logic, QR code generation
- `src/bot.py`: Telegram bot handlers, UI, rate limiting, balance checking, bulk operations, profile management
- `run_dev.py`: Development server with file watching and auto-reload

**Key architectural decisions:**
- **Security-first**: Mnemonics/private keys never logged, held in memory with short TTL only
- **Local-first**: Runs locally, minimal external dependencies
- **Multi-chain support**: Uses bip-utils library for standardized derivation paths
- **Persistence strategy**: Only non-sensitive data (addresses, derivation paths) stored in local SQLite `profiles.db`

## Security Considerations

- **Never log or persist private keys or mnemonics** - they exist only in memory with 3-minute TTL
- **Rate limiting**: 3 requests per minute per user (configurable via RATE_LIMIT_PER_MIN)
- **Bulk operations**: Generate mnemonics in CSVs/ZIPs for backup - users must store offline securely
- **Balance checks**: Optional feature requiring user-provided RPC endpoints

## Configuration

The bot uses environment variables in `.env`:
- `TELEGRAM_BOT_TOKEN`: Required - obtain from BotFather
- `DATA_DIR`: Directory for SQLite database (default: current directory)
- `ADMIN_USER_IDS`: Comma-separated Telegram user IDs with elevated permissions
- RPC endpoints for balance checking: `RPC_ETH`, `RPC_BASE`, `RPC_BSC`, `RPC_POLYGON`, `RPC_AVAXC`
- Optional non-EVM balance support: `ENABLE_BTC_BAL`, `ENABLE_SOL_BAL`, `ENABLE_TON_BAL`

## Key Functions

**In `src/wallets.py`:**
- `generate_wallet(chain: Chain) -> WalletInfo`: Main wallet generation function
- `address_qr_png(address: str) -> bytes`: QR code generation for addresses

**In `src/bot.py`:**
- Enhanced UI handlers: `on_quick_generate_button()`, `on_my_wallets_button()`, etc.
- Interactive callback handlers: `on_help_callback()`, `on_bulk_callback()`, `on_wallet_callback()`
- Balance checking functions for EVM and non-EVM chains  
- Profile management (SQLite operations)
- Bulk job management with ZIP generation
- Enhanced keyboard layouts: `enhanced_chains_kb()`, `main_menu_kb()`

## Development Notes

- Use `run_dev.py` for development - it provides file watching with automatic bot restarts
- The watchdog monitors `*.py`, `*.env`, and `*.md` files in `src/` and project root
- Bot uses aiogram v3 framework with enhanced interactive UI elements
- All crypto operations use the bip-utils library for standardized implementations
- Balance checks are optional and require external RPC provider configuration
- **UI/UX**: Features modern icon-based menu with contextual help and progressive disclosure
- **Code Structure**: Currently monolithic (1600+ lines) - future refactoring planned

## Recent Improvements & Current State

**✅ Completed (August 2025):**
- **Enhanced UI/UX**: Redesigned menu with icons, logical grouping, and better information architecture
- **Interactive Elements**: Context-aware help system, progressive disclosure, confirmation dialogs
- **User Experience**: Streamlined flows for wallet generation, bulk operations, and portfolio management
- **Error Prevention**: Better validation, clearer messaging, and user guidance throughout flows

**🔧 Current Development Priorities:**
- **Code Modularization**: Break down monolithic bot.py into logical modules (handlers, services, ui)
- **Input Validation**: Add comprehensive sanitization for all user inputs
- **Error Handling**: Implement robust exception handling across all async operations
- **Testing Coverage**: Expand beyond basic generation tests to include UI flows and edge cases
- **Documentation**: Complete API documentation and deployment guides

**📋 Technical Debt:**
- Single 1600-line file needs modularization
- Some hardcoded values should be configurable
- Duplicate patterns in balance checking functions
- Limited test coverage for complex user flows

**🎯 Future Enhancements:**
- Database migrations and connection pooling
- Health monitoring and metrics collection
- Performance optimizations for bulk operations
- Enterprise features (team management, audit logs)