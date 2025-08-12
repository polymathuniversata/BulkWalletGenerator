# Supported Chains & Paths

The bot supports the following chains with standard derivations.

- ETH (Ethereum, EVM)
  - Path: `m/44'/60'/0'/0/0`
  - Address: 0x...
- BASE (EVM)
  - Path: `m/44'/60'/0'/0/0`
  - Address: 0x...
- BSC (BNB Smart Chain, EVM)
  - Path: `m/44'/60'/0'/0/0`
  - Address: 0x...
- POLYGON (EVM)
  - Path: `m/44'/60'/0'/0/0`
  - Address: 0x...
- AVAXC (Avalanche C-Chain, EVM)
  - Path: `m/44'/60'/0'/0/0`
  - Address: 0x...
- BTC (Bitcoin, Bech32)
  - Path: `m/84'/0'/0'/0/0`
  - Address: bc1...
- LTC (Litecoin, Bech32)
  - Path: `m/84'/2'/0'/0/0`
  - Address: ltc1...
- DOGE (Dogecoin)
  - Path: `m/44'/3'/0'/0/0`
  - Address: D...
- TRON (TRX)
  - Path: `m/44'/195'/0'/0/0`
  - Address: T...
- XRP (Ripple)
  - Path: `m/44'/144'/0'/0/0`
  - Address: r...
- SOL (Solana)
  - Path: `m/44'/501'/0'/0'`
  - Address: Base58 (public key)
- TON (The Open Network)
  - Path: `m/44'/607'/0'/0/0`
  - Address: ton1... (bip_utils formats the string)

Notes:
- EVM chains reuse ETH path for maximum compatibility.
- BTC/LTC use native segwit (BIP84) for modern wallets.
- Seeds are 12-word BIP39, generated with 128-bit entropy.
