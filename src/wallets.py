from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal, Tuple

import qrcode
from bip_utils import (
    Bip39MnemonicGenerator,
    Bip39WordsNum,
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes,
    Bip84,
    Bip84Coins,
)


Chain = Literal[
    "ETH",
    "BTC",
    "SOL",
    "BASE",
    "BSC",
    "POLYGON",
    "AVAXC",
    "TRON",
    "XRP",
    "DOGE",
    "LTC",
    "TON",
]


@dataclass(frozen=True)
class WalletInfo:
    chain: Chain
    derivation_path: str
    address: str
    mnemonic: str  # 12-word BIP39


def generate_mnemonic_12() -> str:
    """Generate a 12-word BIP39 mnemonic (128-bit entropy)."""
    return Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_12)


def _derive_eth(seed_bytes: bytes) -> Tuple[str, str]:
    # EVM-standard address at ETH path 44'/60'/0'/0/0 for best compatibility across EVM chains.
    bip = (
        Bip44.FromSeed(seed_bytes, Bip44Coins.ETHEREUM)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    addr = bip.PublicKey().ToAddress()
    path = "m/44'/60'/0'/0/0"
    return addr, path


def _derive_ton(seed_bytes: bytes) -> Tuple[str, str]:
    # TON (SLIP-44 coin type 607) uses Ed25519. Bip_utils will format the address appropriately.
    bip = (
        Bip44.FromSeed(seed_bytes, Bip44Coins.TONCOIN)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    addr = bip.PublicKey().ToAddress()
    path = "m/44'/607'/0'/0/0"
    return addr, path


def _derive_btc_bech32(seed_bytes: bytes) -> Tuple[str, str]:
    bip = (
        Bip84.FromSeed(seed_bytes, Bip84Coins.BITCOIN)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    addr = bip.PublicKey().ToAddress()
    path = "m/84'/0'/0'/0/0"
    return addr, path


def _derive_solana(seed_bytes: bytes) -> Tuple[str, str]:
    bip = (
        Bip44.FromSeed(seed_bytes, Bip44Coins.SOLANA)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    # For Solana, address is the Base58-encoded public key
    addr = bip.PublicKey().ToAddress()
    path = "m/44'/501'/0'/0'"
    return addr, path


def _derive_tron(seed_bytes: bytes) -> Tuple[str, str]:
    bip = (
        Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    addr = bip.PublicKey().ToAddress()  # Base58 'T...'
    path = "m/44'/195'/0'/0/0"
    return addr, path


def _derive_xrp(seed_bytes: bytes) -> Tuple[str, str]:
    bip = (
        Bip44.FromSeed(seed_bytes, Bip44Coins.RIPPLE)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    addr = bip.PublicKey().ToAddress()  # 'r...'
    path = "m/44'/144'/0'/0/0"
    return addr, path


def _derive_doge(seed_bytes: bytes) -> Tuple[str, str]:
    bip = (
        Bip44.FromSeed(seed_bytes, Bip44Coins.DOGECOIN)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    addr = bip.PublicKey().ToAddress()  # Legacy P2PKH 'D...'
    path = "m/44'/3'/0'/0/0"
    return addr, path


def _derive_ltc_bech32(seed_bytes: bytes) -> Tuple[str, str]:
    bip = (
        Bip84.FromSeed(seed_bytes, Bip84Coins.LITECOIN)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    addr = bip.PublicKey().ToAddress()  # ltc1...
    path = "m/84'/2'/0'/0/0"
    return addr, path


def generate_wallet(chain: Chain) -> WalletInfo:
    """Generate a 12-word mnemonic and derive the first account address for the given chain.

    Derived paths:
    - ETH:  m/44'/60'/0'/0/0
    - BTC:  m/84'/0'/0'/0/0  (Bech32 P2WPKH)
    - SOL:  m/44'/501'/0'/0'
    """
    mnemonic = generate_mnemonic_12()
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()

    if chain in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC"):
        address, path = _derive_eth(seed_bytes)
    elif chain == "BTC":
        address, path = _derive_btc_bech32(seed_bytes)
    elif chain == "SOL":
        address, path = _derive_solana(seed_bytes)
    elif chain == "TRON":
        address, path = _derive_tron(seed_bytes)
    elif chain == "XRP":
        address, path = _derive_xrp(seed_bytes)
    elif chain == "DOGE":
        address, path = _derive_doge(seed_bytes)
    elif chain == "LTC":
        address, path = _derive_ltc_bech32(seed_bytes)
    elif chain == "TON":
        address, path = _derive_ton(seed_bytes)
    else:
        raise ValueError(f"Unsupported chain: {chain}")

    return WalletInfo(chain=chain, derivation_path=path, address=address, mnemonic=mnemonic)


def address_qr_png(address: str, box_size: int = 8, border: int = 2) -> BytesIO:
    """Return a PNG image (in-memory) of a QR code encoding the address."""
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=border)
    qr.add_data(address)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
