<div align="center">

# 🔐 Telegram Wallet Generator

[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue?style=flat-square&logo=telegram)](https://telegram.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Security](https://img.shields.io/badge/Security-First-red?style=flat-square&logo=shield)](https://github.com)

**A secure, local-first Telegram bot for generating BIP39 wallet addresses across 12+ blockchain networks**

*Generate 12-word mnemonics and derive multi-chain wallet addresses with enterprise-grade security practices*

</div>

---

## 📋 Table of Contents

- [✨ Features](#-features)
- [🔒 Security](#-security)
- [🚀 Quick Start](#-quick-start)
- [🌐 Supported Chains](#-supported-chains)
- [📖 Commands](#-commands)
- [⚙️ Configuration](#️-configuration)
- [🛠️ Development](#️-development)
- [📚 Documentation](#-documentation)
- [🗺️ Roadmap](#️-roadmap)

---

## ✨ Features

- **🔑 Multi-Chain Support**: Generate wallets for 12+ blockchain networks
- **🛡️ Security-First**: In-memory key generation with no persistence
- **📱 Modern UI**: Icon-based interface with contextual help system
- **💾 Bulk Operations**: Generate thousands of wallets with CSV/ZIP export
- **💰 Balance Checking**: Real-time balance queries for supported chains
- **👤 User Profiles**: Store non-sensitive address data locally
- **⚡ Rate Limited**: Built-in protection against abuse
- **🔄 Auto-Delete**: Seed phrases auto-expire after 3 minutes

---

## 🔒 Security

<table>
<tr>
<td>

**🛡️ In-Memory Only**
- No private key persistence
- 3-minute TTL for seed reveals
- Zero sensitive data logging

</td>
<td>

**🚨 Rate Protection** 
- 3 requests per minute per user
- Configurable bulk operation limits
- Admin user privilege system

</td>
<td>

**🔐 Secure Generation**
- BIP39 compliant mnemonics
- Standard derivation paths
- Cryptographically secure randomness

</td>
</tr>
</table>

---

## 🚀 Quick Start

<details>
<summary><b>📋 Prerequisites</b></summary>

- Python 3.10 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Git (optional)

</details>

### 🎯 Installation

```bash
# 1️⃣ Clone the repository
git clone https://github.com/your-username/telegram-wallet-generator.git
cd telegram-wallet-generator

# 2️⃣ Create virtual environment
python -m venv .venv

# 3️⃣ Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate
# Linux/MacOS:
source .venv/bin/activate

# 4️⃣ Install dependencies
pip install -r requirements.txt

# 5️⃣ Configure environment
cp .env.example .env
# Edit .env and add your TELEGRAM_BOT_TOKEN

# 6️⃣ Run the bot
python -m src.bot
```

### 🎮 Development Mode

For development with auto-reload:

```bash
python run_dev.py
```

---

## 🌐 Supported Chains

<table>
<tr>
<th colspan="3">🔗 EVM Compatible Chains</th>
</tr>
<tr>
<td><strong>Ethereum (ETH)</strong><br><code>m/44'/60'/0'/0/0</code></td>
<td><strong>Base</strong><br><code>m/44'/60'/0'/0/0</code></td>
<td><strong>BSC</strong><br><code>m/44'/60'/0'/0/0</code></td>
</tr>
<tr>
<td><strong>Polygon</strong><br><code>m/44'/60'/0'/0/0</code></td>
<td><strong>Avalanche C-Chain</strong><br><code>m/44'/60'/0'/0/0</code></td>
<td></td>
</tr>
<tr>
<th colspan="3">₿ Bitcoin & Derivatives</th>
</tr>
<tr>
<td><strong>Bitcoin (BTC)</strong><br><code>m/84'/0'/0'/0/0</code><br><em>Bech32 (bc1...)</em></td>
<td><strong>Litecoin (LTC)</strong><br><code>m/84'/2'/0'/0/0</code><br><em>Bech32 (ltc1...)</em></td>
<td><strong>Dogecoin (DOGE)</strong><br><code>m/44'/3'/0'/0/0</code><br><em>Legacy (D...)</em></td>
</tr>
<tr>
<th colspan="3">🌟 Other Networks</th>
</tr>
<tr>
<td><strong>Solana (SOL)</strong><br><code>m/44'/501'/0'/0'</code><br><em>Base58 format</em></td>
<td><strong>Tron (TRX)</strong><br><code>m/44'/195'/0'/0/0</code><br><em>Base58 (T...)</em></td>
<td><strong>XRP (Ripple)</strong><br><code>m/44'/144'/0'/0/0</code><br><em>Classic (r...)</em></td>
</tr>
<tr>
<td><strong>TON</strong><br><code>m/44'/607'/0'/0/0</code><br><em>The Open Network</em></td>
<td></td>
<td></td>
</tr>
</table>

---

## 📖 Commands

### 🎯 Core Commands

<table>
<tr>
<th>Command</th>
<th>Description</th>
<th>Example</th>
</tr>
<tr>
<td><code>/start</code>, <code>/help</code></td>
<td>Show usage information and help</td>
<td><code>/start</code></td>
</tr>
<tr>
<td><code>/chains</code></td>
<td>List all supported blockchain networks</td>
<td><code>/chains</code></td>
</tr>
<tr>
<td><code>/generate [CHAIN]</code></td>
<td>Generate mnemonic and address for a chain</td>
<td><code>/generate ETH</code></td>
</tr>
<tr>
<td><code>/version</code></td>
<td>Show supported chains and RPC configuration</td>
<td><code>/version</code></td>
</tr>
</table>

### 💰 Balance & Portfolio Commands  

<table>
<tr>
<th>Command</th>
<th>Description</th>
<th>Requirements</th>
</tr>
<tr>
<td><code>/bal &lt;CHAIN&gt; &lt;ADDR1&gt; [ADDR2...]</code></td>
<td>Check balances for multiple addresses</td>
<td>RPC endpoints configured</td>
</tr>
<tr>
<td><code>/my [CHAIN]</code></td>
<td>Show your saved profile wallets</td>
<td>Profile created</td>
</tr>
<tr>
<td><code>/mycsv</code></td>
<td>Export saved wallets to CSV</td>
<td>Profile with addresses</td>
</tr>
<tr>
<td><code>/mybal &lt;CHAIN&gt;</code></td>
<td>Check balances for your saved addresses</td>
<td>Profile + RPC configured</td>
</tr>
<tr>
<td><code>/clearprofile</code></td>
<td>Delete your saved profile (addresses only)</td>
<td>Existing profile</td>
</tr>
</table>

### 📦 Bulk Operations

<table>
<tr>
<th>Command</th>
<th>Description</th>
<th>Limits</th>
</tr>
<tr>
<td><code>/bulk &lt;CHAIN&gt; &lt;COUNT&gt;</code></td>
<td>Generate multiple wallets (CSV download)</td>
<td>1-20 wallets</td>
</tr>
<tr>
<td><code>/bulkzip &lt;CHAIN&gt; &lt;COUNT&gt;</code></td>
<td>Mass-generate wallets in chunked ZIP</td>
<td>Up to 100k (non-admin)</td>
</tr>
<tr>
<td><code>/jobs</code></td>
<td>List your active bulk ZIP jobs</td>
<td>Admin sees all jobs</td>
</tr>
<tr>
<td><code>/pause &lt;JOB_ID&gt;</code></td>
<td>Pause a running bulk job</td>
<td>Job must be running</td>
</tr>
<tr>
<td><code>/resume &lt;JOB_ID&gt;</code></td>
<td>Resume a paused bulk job</td>
<td>Job must be paused</td>
</tr>
<tr>
<td><code>/cancel &lt;JOB_ID&gt;</code></td>
<td>Cancel a running/paused job</td>
<td>Job must exist</td>
</tr>
</table>

### 🎮 Interactive UI

The bot also provides an icon-based menu with buttons for:

- **🔑 Quick Generate** - Fast wallet generation
- **💰 My Wallets** - View saved addresses  
- **📊 Bulk Operations** - Mass wallet generation
- **❓ Help & FAQ** - Contextual assistance

---

## ⚙️ Configuration

### 🔧 Environment Variables

<details>
<summary><b>📋 Required Configuration</b></summary>

```bash
# .env file
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
```

Get your bot token from [@BotFather](https://t.me/botfather) on Telegram.

</details>

<details>
<summary><b>💰 Balance Checking (Optional)</b></summary>

To enable balance checking with `/bal` and `/mybal` commands:

```bash
# EVM Chain RPC Endpoints
RPC_ETH=https://eth-mainnet.alchemyapi.io/v2/YOUR-API-KEY
RPC_BASE=https://mainnet.base.org
RPC_BSC=https://bsc-dataseed.binance.org/
RPC_POLYGON=https://polygon-rpc.com
RPC_AVAXC=https://api.avax.network/ext/bc/C/rpc

# Non-EVM Balance Support (opt-in)
ENABLE_BTC_BAL=1
BTC_API_BASE=https://blockstream.info/api

ENABLE_SOL_BAL=1  
SOL_RPC_URL=https://api.mainnet-beta.solana.com

ENABLE_TON_BAL=1
TON_API_BASE=https://toncenter.com/api/v2
TON_API_KEY=your_toncenter_api_key
```

**Recommended RPC Providers:**
- [Alchemy](https://alchemy.com) (ETH, POLYGON, BASE)
- [Infura](https://infura.io) (ETH, POLYGON) 
- [QuickNode](https://quicknode.com) (Multi-chain)
- [Ankr](https://ankr.com) (Multi-chain)

</details>

<details>
<summary><b>👥 Admin & Limits</b></summary>

```bash
# Data storage directory
DATA_DIR=./data

# Admin users (Telegram user IDs) - higher bulk limits
ADMIN_USER_IDS=123456789,987654321

# Rate limiting
RATE_LIMIT_PER_MIN=3

# Bulk operation limits
BULKZIP_CSV_CHUNK=10000      # Wallets per CSV chunk
BULKZIP_ZIP_CSVS=10         # Max CSV files per ZIP
BULKZIP_MAX_NONADMIN=100000 # Max wallets for regular users
BULKZIP_MAX_COUNT=1000000   # Max wallets for admins
```

</details>

### 💾 Data Storage

- **`profiles.db`**: SQLite database storing user addresses (non-sensitive data only)
- **`jobs.json`**: Bulk operation job metadata and status
- **Location**: Configurable via `DATA_DIR` (default: current directory)

### 🔒 Security Notes

> ⚠️ **Important Security Practices**
> 
> - **Never share or screenshot seed phrases**  
> - **Store bulk CSV/ZIP files offline securely**
> - **Use your own RPC endpoints for balance checking**
> - **Regularly rotate API keys**
> - **Monitor admin user access**

---

## 🛠️ Development

### 🔧 Development Mode

Use the development server with auto-reload for active development:

```bash
# Install development dependencies
pip install -r requirements.txt

# Run with file watching and auto-restart
python run_dev.py
```

The development server watches for changes in:
- `*.py` files in `src/` directory  
- `.env` configuration files
- `*.md` documentation files

### 🧪 Testing

```bash
# Run comprehensive test suite
python run_tests.py

# Quick validation tests only  
python run_tests.py --quick

# Run with coverage reporting
python run_tests.py --coverage

# Test specific modules
pytest tests/test_validators.py -v
pytest tests/test_error_handling.py -v  
pytest tests/test_ui_flows.py -v
pytest tests/test_integration.py -v
```

### 🏗️ Architecture

- **`src/wallets.py`**: Core wallet generation, BIP39 mnemonics, QR codes
- **`src/bot.py`**: Telegram bot handlers, UI, rate limiting, bulk operations
- **`src/validators.py`**: Input validation and sanitization  
- **`run_dev.py`**: Development server with file watching

---

## 📚 Documentation

<table>
<tr>
<td>

**📖 User Guides**
- [Getting Started](docs/setup.md)
- [Usage Examples](docs/usage.md) 
- [Supported Chains](docs/chains.md)

</td>
<td>

**🔧 Technical Docs**
- [Architecture Overview](docs/architecture.md)
- [API Reference](docs/index.md)
- [Security Model](docs/security.md)

</td>
</tr>
</table>

---

## 🗺️ Roadmap

### 🎯 Current Focus (Q3 2025)

- [x] **Enhanced UI/UX** - Icon-based menus and contextual help
- [x] **Security Hardening** - Input validation and error handling
- [x] **Test Coverage** - Comprehensive test suite (150+ tests)
- [ ] **Code Modularization** - Break down monolithic architecture
- [ ] **Performance Optimization** - Async improvements and caching

### 🔮 Future Plans

- **🐳 Containerization** - Docker support for easy deployment
- **🧪 Testnet Support** - Toggle between mainnet and testnet
- **🔐 Keystore Export** - Encrypted backup options
- **📊 Analytics Dashboard** - Usage metrics and monitoring
- **🏢 Enterprise Features** - Team management and audit logs

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

---

## ⭐ Support

If you find this project useful, please consider giving it a star on GitHub! ⭐

---

<div align="center">

**Built with ❤️ for the crypto community**

[Report Bug](https://github.com/your-username/telegram-wallet-generator/issues) • 
[Request Feature](https://github.com/your-username/telegram-wallet-generator/issues) • 
[Contribute](https://github.com/your-username/telegram-wallet-generator/pulls)

</div>
