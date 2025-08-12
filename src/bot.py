from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import suppress
from typing import Dict, List
from datetime import datetime
import io
import csv
import re
from decimal import Decimal, getcontext
import json
import subprocess
import sys

import aiohttp
import sqlite3
from pathlib import Path
import tempfile
import zipfile
import math
import shutil
import threading
import uuid
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError
from dotenv import load_dotenv

from .wallets import generate_wallet, address_qr_png, Chain
from .error_handling import with_error_handling

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "3"))
ADMIN_USER_IDS = {int(x) for x in os.getenv("ADMIN_USER_IDS", "").replace(" ", "").split(",") if x.isdigit()}
BULK_MAX_COUNT = int(os.getenv("BULK_MAX_COUNT", "1000"))

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("wallet_bot")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Put it in your .env file.")


# Simple in-memory rate limiting: user_id -> [timestamps]
_rl_store: Dict[int, list[float]] = {}

# In-memory pending state for interactive flows (e.g., bulk generate)
_pending_bulk: Dict[int, dict] = {}


def _rate_limited(user_id: int) -> bool:
    now = time.time()
    window_start = now - 60.0
    bucket = _rl_store.setdefault(user_id, [])
    # Drop old timestamps
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    allowed = len(bucket) < RATE_LIMIT_PER_MIN
    if allowed:
        bucket.append(now)
    return not allowed


SUPPORTED_CHAINS: tuple[Chain, ...] = (
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
)


# Commands list for Telegram client '/' suggestions
BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Start and show welcome message"),
    BotCommand(command="help", description="Show usage help"),
    BotCommand(command="menu", description="Show main menu"),
    BotCommand(command="chains", description="List supported chains"),
    BotCommand(command="generate", description="Generate a wallet: /generate ETH"),
    BotCommand(command="bulk", description="Bulk wallets CSV: /bulk ETH 5"),
    BotCommand(command="showseed", description="Reveal your last seed (auto-deletes)"),
    BotCommand(command="bal", description="EVM balances: /bal ETH 0x.. 0x.."),
    BotCommand(command="my", description="Show saved profile wallets"),
    BotCommand(command="mycsv", description="Download your profile wallets CSV"),
    BotCommand(command="mybal", description="Balances for your saved addresses"),
    BotCommand(command="clearprofile", description="Delete your saved profile wallets"),
    BotCommand(command="version", description="Show version and RPC status"),
    BotCommand(command="delete", description="Delete a replied-to message"),
]


async def cmd_start(message: Message):
    user_name = message.from_user.first_name if message.from_user else "there"
    await message.answer(
        f"👋 Welcome {user_name}! This bot generates secure 12-word BIP39 wallets.\n\n"
        "🔑 **Quick Start:**\n"
        "• Tap 'Quick Generate' for instant wallet\n"
        "• View 'My Wallets' to manage saved addresses\n"
        "• Check 'Balances' for portfolio overview\n\n"
        "🛡️ **Security:** Keys are generated locally and never logged. Only you see your seed phrases.",
        reply_markup=main_menu_kb(),
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_menu(message: Message):
    await message.answer("Choose an action:", reply_markup=main_menu_kb())


async def cmd_help(message: Message):
    await message.answer(
        "📚 **Wallet Bot Help**\n\n"
        "🔑 **Wallet Generation:**\n"
        "• Quick Generate → Choose chain → Get wallet\n"
        "• Bulk Operations → Mass generate wallets\n\n"
        "💰 **Portfolio Management:**\n"
        "• My Wallets → View saved addresses\n"
        "• Check Balances → Portfolio overview\n"
        "• Export data as CSV files\n\n"
        "⚡ **Supported Chains:**\n"
        "ETH, BTC, SOL, BASE, BSC, POLYGON, AVAXC, TRON, XRP, DOGE, LTC, TON\n\n"
        "🛡️ **Security Notes:**\n"
        "• Seeds generated locally, never stored\n"
        "• 3-minute seed reveal window\n"
        "• Rate limited for security\n\n"
        "💡 **Pro Tip:** Use bulk operations for multiple wallets at once!",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_version(message: Message):
    chains = ", ".join(SUPPORTED_CHAINS)
    evm_env = [f"{k}={'set' if os.getenv(v) else 'unset'}" for k, v in EVM_RPC_ENV.items()]
    await message.answer(
        "Version info:\n"
        f"Chains: {chains}\n"
        f"EVM RPCs: {', '.join(evm_env)}\n"
        "Build: local run (no git metadata)"
    )


async def cmd_chains(message: Message):
    chains = ", ".join(SUPPORTED_CHAINS)
    await message.answer(f"Supported chains: {chains}")


async def cmd_generate(message: Message):
    if _rate_limited(message.from_user.id):
        await message.answer("Rate limit exceeded. Please try again in a minute.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /generate &lt;CHAIN&gt;\nExample: /generate ETH")
        return

    chain = parts[1].upper()
    if chain not in SUPPORTED_CHAINS:
        await message.answer(f"Unsupported chain. Use one of: {', '.join(SUPPORTED_CHAINS)}")
        return

    await _do_generate(message, chain)


async def cmd_bulk(message: Message):
    # Usage: /bulk <CHAIN> <COUNT>
    if _rate_limited(message.from_user.id):
        await message.answer("Rate limit exceeded. Please try again in a minute.")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(f"Usage: /bulk &lt;CHAIN&gt; &lt;COUNT 1-{BULK_MAX_COUNT}&gt;\nExample: /bulk ETH 5")
        return

    chain = parts[1].upper()
    if chain not in SUPPORTED_CHAINS:
        await message.answer(f"Unsupported chain. Use one of: {', '.join(SUPPORTED_CHAINS)}")
        return

    try:
        count = int(parts[2])
    except ValueError:
        await message.answer(f"COUNT must be an integer between 1 and {BULK_MAX_COUNT}.")
        return

    if not (1 <= count <= BULK_MAX_COUNT):
        await message.answer(f"COUNT must be between 1 and {BULK_MAX_COUNT}.")
        return

    # Generate wallets and build CSV in-memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["index", "chain", "address", "derivation_path", "mnemonic"])
    for i in range(count):
        try:
            info = generate_wallet(chain=chain)
        except Exception:
            # Skip row on failure to avoid leaking errors with sensitive context
            continue
        writer.writerow([i, info.chain, info.address, info.derivation_path, info.mnemonic])
        # Persist to profile (address + path only)
        try:
            ProfileStore.add(message.from_user.id, info.chain, info.address, info.derivation_path)
        except Exception:
            pass

    csv_bytes = buf.getvalue().encode("utf-8")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"wallets_{chain}_{ts}.csv"
    await message.answer_document(
        BufferedInputFile(csv_bytes, filename=filename),
        caption=(
            "CSV contains mnemonics. Store securely and offline.\n"
            "Note: Seeds are generated locally and not stored on the server."
        ),
    )


class SeedStore:
    _data: Dict[int, tuple[str, float]] = {}

    @classmethod
    def put(cls, user_id: int, mnemonic: str, ttl_seconds: int = 180) -> None:
        cls._data[user_id] = (mnemonic, time.time() + ttl_seconds)

    @classmethod
    def take(cls, user_id: int) -> str | None:
        rec = cls._data.pop(user_id, None)
        if not rec:
            return None
        mnemonic, expires = rec
        if time.time() > expires:
            return None
        return mnemonic


async def cmd_showseed(message: Message):
    # One-time reveal
    mnemonic = SeedStore.take(message.from_user.id)
    if not mnemonic:
        await message.answer("No seed available to show or it has expired.")
        return

    # Send and schedule auto-delete
    sent = await message.answer(f"Your 12-word seed (copy carefully):\n<code>{mnemonic}</code>", parse_mode=ParseMode.HTML)
    await message.answer("This message will be deleted in 30 seconds. Use /delete to remove immediately.")

    async def _auto_delete():
        await asyncio.sleep(30)
        with suppress(Exception):
            await sent.delete()

    asyncio.create_task(_auto_delete())


async def cmd_delete(message: Message):
    # A convenience command: asks user to reply to the seed message then deletes it, or no-op if not found.
    if message.reply_to_message:
        with suppress(Exception):
            await message.reply_to_message.delete()
        await message.answer("Deleted.")
    else:
        await message.answer("Reply to the message you want to delete and send /delete.")


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="🔑 Quick Generate"), KeyboardButton(text="📊 View Chains")],
            [KeyboardButton(text="💰 My Wallets"), KeyboardButton(text="🔄 Bulk Operations")],
            [KeyboardButton(text="⚖️ Check Balances"), KeyboardButton(text="❓ Help & Info")],
        ],
        one_time_keyboard=False,
        input_field_placeholder="Choose an option or type a command..."
    )


def enhanced_chains_kb(prefix: str = "gen:") -> InlineKeyboardMarkup:
    """Enhanced chain selection with icons and better organization"""
    # Group chains by category for better UX
    evm_chains = ["ETH", "BASE", "BSC", "POLYGON", "AVAXC"]
    btc_like = ["BTC", "LTC", "DOGE"]
    other_chains = ["SOL", "TRON", "XRP", "TON"]
    
    # Chain icons mapping
    chain_icons = {
        "ETH": "🔶", "BTC": "🧡", "SOL": "☀️", "BASE": "🔵", "BSC": "🟡",
        "POLYGON": "🟣", "AVAXC": "❄️", "TRON": "🔴", "XRP": "💰", "DOGE": "🐶",
        "LTC": "🥈", "TON": "🔷"
    }
    
    buttons = []
    # EVM chains row
    buttons.append([InlineKeyboardButton(text=f"{chain_icons.get(ch, '🔗')} {ch}", callback_data=f"{prefix}{ch}") for ch in evm_chains[:3]])
    buttons.append([InlineKeyboardButton(text=f"{chain_icons.get(ch, '🔗')} {ch}", callback_data=f"{prefix}{ch}") for ch in evm_chains[3:]])
    # BTC-like chains
    buttons.append([InlineKeyboardButton(text=f"{chain_icons.get(ch, '🔗')} {ch}", callback_data=f"{prefix}{ch}") for ch in btc_like])
    # Other chains
    buttons.append([InlineKeyboardButton(text=f"{chain_icons.get(ch, '🔗')} {ch}", callback_data=f"{prefix}{ch}") for ch in other_chains])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def chains_inline_kb(prefix: str = "gen:") -> InlineKeyboardMarkup:
    # Legacy function for backward compatibility
    return enhanced_chains_kb(prefix)


def generate_mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Single", callback_data="mode:single")],
            [InlineKeyboardButton(text="Bulk", callback_data="mode:bulk")],
        ]
    )


async def on_quick_generate_button(message: Message):
    if _rate_limited(message.from_user.id):
        await message.answer("⏰ Rate limit exceeded. Please wait a moment before generating again.")
        return
    await message.answer(
        "🔑 **Quick Generate**\n\nSelect a blockchain to generate a secure wallet:", 
        reply_markup=enhanced_chains_kb(),
        parse_mode=ParseMode.MARKDOWN
    )


async def on_generate_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("gen:"):
        return
    chain = cb.data.split(":", 1)[1]
    # Acknowledge to remove loading state
    with suppress(Exception):
        await cb.answer()
    await _do_generate(cb.message, chain)


async def on_generate_mode_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("mode:"):
        return
    mode = cb.data.split(":", 1)[1]
    with suppress(Exception):
        await cb.answer()
    if mode == "single":
        await cb.message.answer("Select a chain:", reply_markup=chains_inline_kb(prefix="gen:"))
    elif mode == "bulk":
        # Start bulk flow: ask for count first
        _pending_bulk[cb.from_user.id] = {"stage": "count"}
        await cb.message.answer(f"Send the number of wallets to create (1-{BULK_MAX_COUNT}), then you'll choose a chain.")


async def on_bulk_count_input(message: Message):
    state = _pending_bulk.get(message.from_user.id)
    if not state or state.get("stage") != "count":
        return  # not in bulk count collection
    
    txt = (message.text or "").strip()
    try:
        count = int(txt)
    except ValueError:
        bulk_type = state.get("type", "csv")
        max_count = 1000 if bulk_type == "csv" else MAX_COUNT
        await message.answer(f"Please send a number between 1 and {max_count}.")
        return
    
    bulk_type = state.get("type", "csv")
    
    if bulk_type == "csv":
        if not (1 <= count <= 1000):
            await message.answer("CSV generation supports 1-1000 wallets.")
            return
        prefix = "genbulk:"
    else:  # zip
        max_allowed = MAX_COUNT if is_admin(message.from_user.id) else MAX_COUNT_NONADMIN
        if not (1000 <= count <= max_allowed):
            await message.answer(f"ZIP generation requires 1000-{max_allowed} wallets.")
            return
        prefix = "genzip:"
    
    # Save and advance to chain selection
    _pending_bulk[message.from_user.id] = {"stage": "chain", "count": count, "type": bulk_type}
    await message.answer(
        f"✅ Count set to {count:,} wallets.\n\nNow select a blockchain:", 
        reply_markup=enhanced_chains_kb(prefix=prefix),
        parse_mode=ParseMode.MARKDOWN
    )


async def on_generate_bulk_callback(cb: CallbackQuery):
    if not cb.data or not (cb.data.startswith("genbulk:") or cb.data.startswith("genzip:")):
        return
    
    is_zip = cb.data.startswith("genzip:")
    chain = cb.data.split(":", 1)[1]
    state = _pending_bulk.get(cb.from_user.id)
    
    if not state or state.get("stage") != "chain" or "count" not in state:
        await safe_answer_callback(cb)
        await cb.message.answer("Please start bulk generation via 'Bulk Operations' first.")
        return
    
    count = int(state["count"])
    
    with suppress(Exception):
        await cb.answer()
    
    if is_zip:
        # Redirect to bulkzip command functionality
        fake_message = type('MockMessage', (), {
            'text': f'/bulkzip {chain} {count}',
            'from_user': cb.from_user,
            'answer': cb.message.answer,
            'answer_document': cb.message.answer_document
        })()
        await cmd_bulkzip(fake_message)
    else:
        # Execute CSV bulk generation
        await cb.message.answer(f"🔄 Generating {count:,} {chain} wallets...")
        
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["index", "chain", "address", "derivation_path", "mnemonic"])
        
        for i in range(count):
            try:
                info = generate_wallet(chain=chain)
            except Exception:
                continue
            writer.writerow([i, info.chain, info.address, info.derivation_path, info.mnemonic])
            try:
                ProfileStore.add(cb.from_user.id, info.chain, info.address, info.derivation_path)
            except Exception:
                pass
        
        csv_bytes = buf.getvalue().encode("utf-8")
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"wallets_{chain}_{count}_{ts}.csv"
        
        await cb.message.answer_document(
            BufferedInputFile(csv_bytes, filename=filename),
            caption=(
                f"✅ **Generated {count:,} {chain} wallets**\n\n"
                "⚠️ CSV contains seed phrases - store securely offline!\n"
                "💾 Wallets automatically saved to your profile."
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Clear state
    _pending_bulk.pop(cb.from_user.id, None)


async def on_show_seed_button(message: Message):
    await cmd_showseed(message)


async def on_view_chains_button(message: Message):
    chains_info = {
        "ETH": "Ethereum - Smart contracts, DeFi, NFTs",
        "BTC": "Bitcoin - Digital gold, store of value", 
        "SOL": "Solana - Fast, low-cost transactions",
        "BASE": "Base - Coinbase's L2 solution",
        "BSC": "Binance Smart Chain - DeFi ecosystem",
        "POLYGON": "Polygon - Ethereum scaling solution",
        "AVAXC": "Avalanche C-Chain - Fast finality",
        "TRON": "TRON - Content & entertainment",
        "XRP": "XRP Ledger - Cross-border payments",
        "DOGE": "Dogecoin - Meme coin with utility",
        "LTC": "Litecoin - Silver to Bitcoin's gold",
        "TON": "The Open Network - Telegram integration"
    }
    
    chain_text = "📊 **Supported Blockchains**\n\n"
    for chain, desc in chains_info.items():
        chain_text += f"• **{chain}**: {desc}\n"
    
    chain_text += "\n💡 **Tip**: Each chain uses industry-standard derivation paths for maximum compatibility."
    
    await message.answer(chain_text, parse_mode=ParseMode.MARKDOWN)

# Legacy compatibility
async def on_chains_button(message: Message):
    await on_view_chains_button(message)


async def on_help_info_button(message: Message):
    help_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Commands Guide", callback_data="help:commands")],
            [InlineKeyboardButton(text="🛡️ Security Info", callback_data="help:security")],
            [InlineKeyboardButton(text="🔧 Setup & Config", callback_data="help:setup")],
            [InlineKeyboardButton(text="❓ FAQ", callback_data="help:faq")],
        ]
    )
    await message.answer(
        "❓ **Help & Information**\n\nWhat would you like to learn about?",
        reply_markup=help_kb,
        parse_mode=ParseMode.MARKDOWN
    )

# Legacy compatibility  
async def on_help_button(message: Message):
    await on_help_info_button(message)


async def on_bulk_operations_button(message: Message):
    if _rate_limited(message.from_user.id):
        await message.answer("⏰ Rate limit exceeded. Please wait before starting bulk operations.")
        return
        
    bulk_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Bulk CSV (1-1000)", callback_data="bulk:csv")],
            [InlineKeyboardButton(text="🗃️ Bulk ZIP (1000+)", callback_data="bulk:zip")],
            [InlineKeyboardButton(text="📊 View Active Jobs", callback_data="bulk:jobs")],
        ]
    )
    
    await message.answer(
        "🔄 **Bulk Operations**\n\n"
        "📄 **CSV**: Generate up to 1000 wallets as CSV\n"
        "🗃️ **ZIP**: Mass generate 1000+ wallets in compressed archives\n"
        "📊 **Jobs**: Monitor your bulk generation progress\n\n"
        "⚠️ **Note**: Bulk files contain seed phrases. Store securely offline!",
        reply_markup=bulk_kb,
        parse_mode=ParseMode.MARKDOWN
    )


async def on_my_wallets_button(message: Message):
    rows = ProfileStore.list(message.from_user.id)
    if not rows:
        await message.answer(
            "💰 **My Wallets**\n\n"
            "💭 No wallets saved yet.\n\n"
            "Generate your first wallet using 'Quick Generate' to get started!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Create summary by chain
    counts = {}
    for ch, _, __, ___ in rows:
        counts[ch] = counts.get(ch, 0) + 1
    
    summary_text = "💰 **My Wallets**\n\n"
    total_wallets = len(rows)
    summary_text += f"📊 **Total**: {total_wallets} wallet{'s' if total_wallets != 1 else ''}\n\n"
    
    for chain, count in sorted(counts.items()):
        summary_text += f"• **{chain}**: {count} wallet{'s' if count != 1 else ''}\n"
    
    wallet_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 View by Chain", callback_data="wallet:view_by_chain")],
            [InlineKeyboardButton(text="📄 Export CSV", callback_data="wallet:export_csv")],
            [InlineKeyboardButton(text="⚖️ Check Balances", callback_data="wallet:check_balances")],
            [InlineKeyboardButton(text="🗑️ Clear All", callback_data="wallet:clear_confirm")],
        ]
    )
    
    await message.answer(summary_text, reply_markup=wallet_kb, parse_mode=ParseMode.MARKDOWN)

# Legacy compatibility
async def on_my_button(message: Message):
    await on_my_wallets_button(message)


async def on_mycsv_button(message: Message):
    await cmd_mycsv(message)

async def on_show_seed_button(message: Message):
    # Enhanced seed reveal with better UX
    mnemonic = SeedStore.take(message.from_user.id)
    if not mnemonic:
        await message.answer(
            "🔑 **Show Seed**\n\n"
            "💭 No seed available to show.\n\n"
            "Seeds are only available for 3 minutes after generation. Generate a new wallet to get a fresh seed.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Send seed with enhanced formatting and security warning
    sent = await message.answer(
        "🔑 **Your 12-Word Seed Phrase**\n\n"
        f"📝 `{mnemonic}`\n\n"
        "⚠️ **SECURITY WARNING:**\n"
        "• This message will auto-delete in 30 seconds\n"
        "• Screenshot and store offline securely\n"
        "• Never share or send to anyone\n"
        "• Use /delete to remove immediately",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Auto-delete after 30 seconds
    async def _auto_delete():
        await asyncio.sleep(30)
        with suppress(Exception):
            await sent.delete()
            await message.answer("🗑️ Seed message auto-deleted for security.")
    
    asyncio.create_task(_auto_delete())


async def on_bulkzip_button(message: Message):
    await message.answer("Usage: /bulkzip &lt;CHAIN&gt; &lt;COUNT&gt;\nExample: /bulkzip ETH 10000\nNote: This will generate many seeds to CSV chunks and compress to ZIP(s). Handle seeds securely.")


async def on_check_balances_button(message: Message):
    rows = ProfileStore.list(message.from_user.id)
    if not rows:
        await message.answer(
            "⚖️ **Check Balances**\n\n"
            "💭 No saved wallets found.\n\n"
            "Generate wallets first using 'Quick Generate' to check balances.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Group by supported balance chains
    supported_balance_chains = set()
    for chain, _, __, ___ in rows:
        if chain in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC", "BTC", "SOL", "TON"):
            supported_balance_chains.add(chain)
    
    if not supported_balance_chains:
        await message.answer(
            "⚖️ **Check Balances**\n\n"
            "💭 No wallets with balance checking support found.\n\n"
            "Supported: ETH, BASE, BSC, POLYGON, AVAXC, BTC, SOL, TON",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Create balance check options
    balance_kb_rows = []
    for chain in sorted(supported_balance_chains):
        count = sum(1 for ch, _, __, ___ in rows if ch == chain)
        balance_kb_rows.append([
            InlineKeyboardButton(
                text=f"⚖️ {chain} ({count} wallet{'s' if count != 1 else ''})", 
                callback_data=f"balance:{chain}"
            )
        ])
    
    balance_kb_rows.append([
        InlineKeyboardButton(text="📊 Portfolio Overview", callback_data="balance:portfolio")
    ])
    
    await message.answer(
        "⚖️ **Check Balances**\n\nSelect a blockchain to check your wallet balances:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=balance_kb_rows),
        parse_mode=ParseMode.MARKDOWN
    )

# Legacy compatibility
async def on_balance_button(message: Message):
    await on_check_balances_button(message)


def mybal_mode_kb(chain: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Single", callback_data=f"mybalmode:{chain}:single")],
            [InlineKeyboardButton(text="Bulk (All)", callback_data=f"mybalmode:{chain}:bulk_all")],
        ]
    )


def mybal_single_list_kb(addresses: list[str], chain: str, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    start = page * per_page
    end = min(len(addresses), start + per_page)
    rows = []
    for idx in range(start, end):
        addr = addresses[idx]
        label = f"{idx+1}. {addr[:6]}…{addr[-4:]}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"mybalsingle:{chain}:{idx}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"mybalsingle:nav:{chain}:{page-1}"))
    if end < len(addresses):
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"mybalsingle:nav:{chain}:{page+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="No addresses", callback_data="noop")]])


@with_error_handling(context="do_generate", user_message="Failed to generate wallet")
async def _do_generate(message: Message, chain: str):
    try:
        # Validate chain one more time for safety
        validated_chain = safe_chain(chain)
        info = generate_wallet(chain=validated_chain)  # Do NOT log mnemonic or privkeys
    except ValidationError as e:
        await message.answer(f"❌ {e.message}")
        return
    except Exception as e:
        logger.exception("Generation failed: %s", e)
        await message.answer("❌ Failed to generate wallet. Please try again.")
        return

    # Try to fetch live balance for EVM chains (ETH, BASE, BSC, POLYGON, AVAXC)
    balance_line = ""
    if info.chain in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC"):
        try:
            balances = await _evm_balances(info.chain, [info.address])
            if balances:
                _, _, eth = balances[0]
                balance_line = f"Balance: {eth} ETH-equivalent\n"
        except Exception:
            # Ignore balance errors here to keep generation fast and reliable
            balance_line = ""

    text = (
        f"Chain: {info.chain}\n"
        f"Address: <code>{info.address}</code>\n"
        f"Path: <code>{info.derivation_path}</code>\n"
        f"{balance_line}"
        "\nTap the QR image to save. Use 'Show Seed' to reveal the seed once.")
    await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=main_menu_kb())

    png = address_qr_png(info.address)
    await message.answer_photo(BufferedInputFile(png.read(), filename=f"{info.chain}_address.png"), caption=f"{info.chain} address QR")

    # Save non-sensitive wallet info to profile
    try:
        ProfileStore.add(message.from_user.id, info.chain, info.address, info.derivation_path)
    except Exception:
        pass

    SeedStore.put(message.from_user.id, info.mnemonic, ttl_seconds=180)  # 3 minutes
    
    # Enhanced seed reveal options
    seed_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Show Seed Phrase", callback_data="seed:show")],
            [InlineKeyboardButton(text="📄 Generate Another", callback_data="gen:quickgen")],
        ]
    )
    
    await message.answer(
        "✅ **Wallet Generated Successfully!**\n\n"
        "🔑 Your seed phrase is ready (expires in 3 minutes)\n"
        "💾 Address automatically saved to your profile\n\n"
        "💡 **Next Steps:**\n"
        "• Reveal your seed phrase to back it up\n"
        "• Generate more wallets if needed",
        reply_markup=seed_kb,
        parse_mode=ParseMode.MARKDOWN
    )


async def run() -> None:
    dp = Dispatcher()
    dp.message.register(cmd_start, Command(commands=["start"]))
    dp.message.register(cmd_help, Command(commands=["help"]))
    dp.message.register(cmd_menu, Command(commands=["menu"]))
    dp.message.register(cmd_chains, Command(commands=["chains"]))
    dp.message.register(cmd_generate, Command(commands=["generate"]))
    dp.message.register(cmd_bulk, Command(commands=["bulk"]))
    dp.message.register(cmd_showseed, Command(commands=["showseed"]))
    dp.message.register(cmd_bal, Command(commands=["bal"]))
    dp.message.register(cmd_my, Command(commands=["my"]))
    dp.message.register(cmd_mycsv, Command(commands=["mycsv"]))
    dp.message.register(cmd_mybal, Command(commands=["mybal"]))
    dp.message.register(cmd_clearprofile, Command(commands=["clearprofile"]))
    dp.message.register(cmd_version, Command(commands=["version"]))
    dp.message.register(cmd_delete, Command(commands=["delete"]))
    dp.message.register(cmd_jobs, Command(commands=["jobs"]))
    dp.message.register(cmd_pause, Command(commands=["pause"]))
    dp.message.register(cmd_resume, Command(commands=["resume"]))
    dp.message.register(cmd_cancel, Command(commands=["cancel"]))
    dp.message.register(cmd_bulkzip, Command(commands=["bulkzip"]))

    # New enhanced UI buttons
    dp.message.register(on_quick_generate_button, F.text.casefold().in_(["🔑 quick generate", "quick generate"]))
    dp.message.register(on_view_chains_button, F.text.casefold().in_(["📊 view chains", "view chains"]))
    dp.message.register(on_my_wallets_button, F.text.casefold().in_(["💰 my wallets", "my wallets"]))
    dp.message.register(on_bulk_operations_button, F.text.casefold().in_(["🔄 bulk operations", "bulk operations"]))
    dp.message.register(on_check_balances_button, F.text.casefold().in_(["⚖️ check balances", "check balances"]))
    dp.message.register(on_help_info_button, F.text.casefold().in_(["❓ help & info", "help & info", "help"]))
    
    # Legacy support for backward compatibility
    dp.message.register(on_quick_generate_button, F.text.casefold() == "generate wallet")
    dp.message.register(on_show_seed_button, F.text.casefold() == "show seed")
    dp.message.register(on_view_chains_button, F.text.casefold() == "chains")
    dp.message.register(on_my_wallets_button, F.text.casefold() == "my profile")
    dp.message.register(on_check_balances_button, F.text.casefold() == "balance")
    # Bulk count free-text input (exclude slash-commands so we don't shadow them)
    dp.message.register(on_bulk_count_input, F.text & ~F.text.startswith("/"))
    dp.message.register(on_mycsv_button, F.text.casefold() == "my csv")
    
    # New callback for wallet view by chain
    dp.callback_query.register(on_walletview_callback, F.data.startswith("walletview:"))
    dp.message.register(on_mycsv_button, F.text.casefold() == "my csv")

    # Enhanced inline keyboard callbacks
    dp.callback_query.register(on_generate_callback, F.data.startswith("gen:"))
    dp.callback_query.register(on_generate_mode_callback, F.data.startswith("mode:"))
    dp.callback_query.register(on_generate_bulk_callback, F.data.startswith("genbulk:"))
    dp.callback_query.register(on_generate_bulk_callback, F.data.startswith("genzip:"))
    dp.callback_query.register(on_help_callback, F.data.startswith("help:"))
    dp.callback_query.register(on_bulk_callback, F.data.startswith("bulk:"))
    dp.callback_query.register(on_wallet_callback, F.data.startswith("wallet:"))
    dp.callback_query.register(on_balance_callback, F.data.startswith("balance:"))
    dp.callback_query.register(on_mybal_callback, F.data.startswith("mybal:"))
    dp.callback_query.register(on_mybal_mode_callback, F.data.startswith("mybalmode:"))
    dp.callback_query.register(on_mybal_single_nav, F.data.startswith("mybalsingle:nav:"))
    dp.callback_query.register(on_mybal_single_pick, F.data.startswith("mybalsingle:"))
    dp.callback_query.register(on_job_callback, F.data.startswith("job:"))
    dp.callback_query.register(on_seed_callback, F.data.startswith("seed:"))

    # Initialize profile store
    with suppress(Exception):
        ProfileStore.init()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # Register '/' command suggestions in the Telegram client
    with suppress(Exception):
        await bot.set_my_commands(BOT_COMMANDS)
    backoff = 1.0
    max_backoff = 30.0
    logger.info("Bot started. Press Ctrl+C to stop.")
    try:
        while True:
            try:
                await dp.start_polling(bot)
                # Normal stop (e.g., dp.stop_polling), break out
                break
            except TelegramNetworkError as e:
                logger.warning(
                    "Network error: %s. Retrying in %.1fs...", str(e), backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(max_backoff, backoff * 1.618)
                continue
            except asyncio.CancelledError:
                # Treat task cancellation as graceful stop (e.g., SIGTERM)
                logger.info("Polling task cancelled. Shutting down gracefully...")
                break
            except KeyboardInterrupt:
                logger.info("Shutdown requested (KeyboardInterrupt).")
                break
            except Exception as e:
                logger.exception("Unrecoverable error: %s", e)
                break
    finally:
        with suppress(Exception):
            # Ensure bot session is closed gracefully
            await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        # Suppress traceback on Ctrl+C at top-level
        logger.info("Exited by user (KeyboardInterrupt). Goodbye.")
    except SystemExit:
        # Allow sys.exit() without noisy traceback
        logger.info("System exit requested. Goodbye.")


# ---------- Bulk balance checks (EVM) ----------

EVM_RPC_ENV = {
    "ETH": "RPC_ETH",
    "BASE": "RPC_BASE",
    "BSC": "RPC_BSC",
    "POLYGON": "RPC_POLYGON",
    "AVAXC": "RPC_AVAXC",
}

_EVM_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
getcontext().prec = 80


def _get_evm_rpc(chain: str) -> str:
    env_key = EVM_RPC_ENV.get(chain)
    if not env_key:
        raise ValueError("Unsupported chain for EVM balance check")
    url = os.getenv(env_key, "").strip()
    if not url:
        raise RuntimeError(f"Missing RPC endpoint: set {env_key} in .env")
    return url


def _wei_to_eth(wei_hex: str) -> Decimal:
    # wei_hex like '0x...' -> int -> Decimal ether
    iv = int(wei_hex, 16)
    return Decimal(iv) / Decimal(10**18)


async def _evm_balances(chain: str, addresses: List[str]) -> List[tuple[str, str, Decimal]]:
    rpc = _get_evm_rpc(chain)
    # Build JSON-RPC batch
    batch = []
    for i, addr in enumerate(addresses):
        batch.append({
            "jsonrpc": "2.0",
            "id": i,
            "method": "eth_getBalance",
            "params": [addr, "latest"],
        })
    async with aiohttp.ClientSession() as session:
        async with session.post(rpc, data=json.dumps(batch), headers={"Content-Type": "application/json"}, timeout=30) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"RPC error {resp.status}: {text[:200]}")
            data = await resp.json(content_type=None)
    # Some RPCs may return non-ordered results; map by id
    results = {item.get("id"): item for item in data if isinstance(item, dict)}
    out: List[tuple[str, str, Decimal]] = []
    for i, addr in enumerate(addresses):
        item = results.get(i, {})
        result_hex = (item.get("result") or "0x0") if isinstance(item, dict) else "0x0"
        try:
            eth = _wei_to_eth(result_hex)
        except Exception:
            eth = Decimal(0)
            result_hex = "0x0"
        out.append((addr, result_hex, eth))
    return out


def _chunk(seq: List[str], size: int) -> List[List[str]]:
    return [seq[i:i+size] for i in range(0, len(seq), size)]


async def _evm_balances_chunked(chain: str, addresses: List[str], chunk_size: int = 100) -> List[tuple[str, str, Decimal]]:
    """Fetch EVM balances for an arbitrary number of addresses by batching requests.

    Many providers have payload/array limits; chunk to stay reliable.
    """
    results: List[tuple[str, str, Decimal]] = []
    for batch in _chunk(addresses, chunk_size):
        part = await _evm_balances(chain, batch)
        results.extend(part)
    return results


@with_error_handling(context="cmd_bal", user_message="Failed to check balances")
async def cmd_bal(message: Message):
    if not message.text:
        await message.answer("❌ No command text received. Please try again.")
        return
        
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "📝 **Usage**: `/bal <EVM_CHAIN> <ADDR1> [ADDR2 ...]`\n\n"
            "**Example**: `/bal ETH 0xabc... 0xdef...`\n\n"
            "**Tip**: Use `/mybal <EVM_CHAIN>` to check balances for your saved addresses.\n\n"
            "**Supported chains**: ETH, BASE, BSC, POLYGON, AVAXC",
            parse_mode="Markdown"
        )
        return
    
    try:
        chain = safe_chain(parts[1])
        if chain not in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC"):
            raise ValidationError("Balance checking only supported for EVM chains: ETH, BASE, BSC, POLYGON, AVAXC")
    except ValidationError as e:
        await message.answer(f"❌ {e.message}")
        return

    # If only chain was provided, fall back to user's saved addresses (same as /mybal <CHAIN>)
    if len(parts) == 2:
        # Delegate to the shared implementation used by /mybal
        await _mybal_for_chain(message, chain)
        return

    # Otherwise parse provided addresses
    addrs: list[str] = []
    for a in parts[2:]:
        if _EVM_ADDR_RE.match(a):
            addrs.append(a)
    if not addrs:
        await message.answer(
            "No valid EVM addresses provided.\n"
            "Tip: You can run /bal &lt;EVM_CHAIN&gt; alone to use your saved addresses (or /mybal &lt;EVM_CHAIN&gt;)."
        )
        return
    try:
        balances = await _evm_balances_chunked(chain, addrs)
    except Exception as e:
        await message.answer(f"RPC error: {str(e)[:200]}")
        return

    # Build CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["chain", "address", "balance_wei_hex", "balance_ether"])
    total_eth = Decimal(0)
    for addr, wei_hex, eth in balances:
        total_eth += eth
        writer.writerow([chain, addr, wei_hex, f"{eth}"])

    csv_bytes = buf.getvalue().encode("utf-8")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"balances_{chain}_{ts}.csv"
    await message.answer_document(
        BufferedInputFile(csv_bytes, filename=filename),
        caption=(
            f"Chain: {chain}\nAddresses: {len(balances)}\nTotal: {total_eth} ETH-equivalent"
        ),
    )


# ---------- Optional non-EVM balances (BTC, SOL, TON) ----------

# Env flags and endpoints
ENABLE_BTC_BAL = os.getenv("ENABLE_BTC_BAL", "0") == "1"
BTC_API_BASE = os.getenv("BTC_API_BASE", "https://blockstream.info/api").rstrip("/")

ENABLE_SOL_BAL = os.getenv("ENABLE_SOL_BAL", "0") == "1"
SOL_RPC_URL = os.getenv("SOL_RPC_URL", "").strip()

ENABLE_TON_BAL = os.getenv("ENABLE_TON_BAL", "0") == "1"
TON_API_BASE = os.getenv("TON_API_BASE", "").rstrip("/")
TON_API_KEY = os.getenv("TON_API_KEY", "").strip()


async def _btc_balances(addresses: List[str]) -> List[tuple[str, int, Decimal]]:
    """Returns list of (address, sats, btc). Confirmed balance only."""
    out: List[tuple[str, int, Decimal]] = []
    async with aiohttp.ClientSession() as session:
        for addr in addresses:
            url = f"{BTC_API_BASE}/address/{addr}"
            try:
                async with session.get(url, timeout=20) as resp:
                    if resp.status != 200:
                        out.append((addr, 0, Decimal(0)))
                        continue
                    data = await resp.json(content_type=None)
            except Exception:
                out.append((addr, 0, Decimal(0)))
                continue
            chain_stats = data.get("chain_stats", {}) if isinstance(data, dict) else {}
            funded = int(chain_stats.get("funded_txo_sum", 0))
            spent = int(chain_stats.get("spent_txo_sum", 0))
            sats = max(0, funded - spent)
            btc = Decimal(sats) / Decimal(10**8)
            out.append((addr, sats, btc))
    return out


async def _sol_balances(addresses: List[str]) -> List[tuple[str, int, Decimal]]:
    """Uses Solana RPC getBalance. Returns (address, lamports, SOL)."""
    if not SOL_RPC_URL:
        raise RuntimeError("Missing SOL_RPC_URL")
    batch = []
    for i, a in enumerate(addresses):
        batch.append({
            "jsonrpc": "2.0",
            "id": i,
            "method": "getBalance",
            "params": [a],
        })
    async with aiohttp.ClientSession() as session:
        async with session.post(SOL_RPC_URL, data=json.dumps(batch), headers={"Content-Type": "application/json"}, timeout=30) as resp:
            if resp.status != 200:
                txt = await resp.text()
                raise RuntimeError(f"SOL RPC error {resp.status}: {txt[:200]}")
            data = await resp.json(content_type=None)
    results = {item.get("id"): item for item in data if isinstance(item, dict)}
    out: List[tuple[str, int, Decimal]] = []
    for i, addr in enumerate(addresses):
        lamports = 0
        item = results.get(i, {})
        if isinstance(item, dict):
            res = item.get("result") or {}
            if isinstance(res, dict):
                lamports = int(res.get("value", 0))
        out.append((addr, lamports, Decimal(lamports) / Decimal(10**9)))
    return out


async def _ton_balances(addresses: List[str]) -> List[tuple[str, int, Decimal]]:
    """Uses TON API (toncenter-compatible) getAddressInformation. Returns (address, nanotons, TON)."""
    if not TON_API_BASE:
        raise RuntimeError("Missing TON_API_BASE")
    out: List[tuple[str, int, Decimal]] = []
    params_key = f"&api_key={TON_API_KEY}" if TON_API_KEY else ""
    async with aiohttp.ClientSession() as session:
        for addr in addresses:
            url = f"{TON_API_BASE}/getAddressInformation?address={addr}{params_key}"
            try:
                async with session.get(url, timeout=20) as resp:
                    if resp.status != 200:
                        out.append((addr, 0, Decimal(0)))
                        continue
                    data = await resp.json(content_type=None)
            except Exception:
                out.append((addr, 0, Decimal(0)))
                continue
            ok = bool(data.get("ok")) if isinstance(data, dict) else False
            if not ok:
                out.append((addr, 0, Decimal(0)))
                continue
            result = data.get("result", {})
            bal = int(result.get("balance", 0)) if isinstance(result, dict) else 0
            out.append((addr, bal, Decimal(bal) / Decimal(10**9)))
    return out

# ---------- Profiles (SQLite) ----------

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).resolve()
DB_PATH = DATA_DIR / "profiles.db"
JOBS_JSON = DATA_DIR / "jobs.json"


class ProfileStore:
    _conn: sqlite3.Connection | None = None

    @classmethod
    def init(cls) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls._conn = sqlite3.connect(DB_PATH)
        cls._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallets (
                user_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                derivation_path TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, chain, address)
            )
            """
        )
        cls._conn.commit()

    @classmethod
    def add(cls, user_id: int, chain: str, address: str, derivation_path: str) -> None:
        if cls._conn is None:
            cls.init()
        try:
            cls._conn.execute(
                "INSERT OR IGNORE INTO wallets (user_id, chain, address, derivation_path, created_at) VALUES (?,?,?,?,?)",
                (user_id, chain, address, derivation_path, int(time.time())),
            )
            cls._conn.commit()
        except Exception:
            pass

    @classmethod
    def list(cls, user_id: int, chain: str | None = None) -> list[tuple[str, str, str, int]]:
        if cls._conn is None:
            cls.init()
        cur = cls._conn.cursor()
        if chain:
            cur.execute("SELECT chain,address,derivation_path,created_at FROM wallets WHERE user_id=? AND chain=? ORDER BY created_at DESC", (user_id, chain))
        else:
            cur.execute("SELECT chain,address,derivation_path,created_at FROM wallets WHERE user_id=? ORDER BY created_at DESC", (user_id,))
        return cur.fetchall()

    @classmethod
    def clear(cls, user_id: int) -> int:
        if cls._conn is None:
            cls.init()
        cur = cls._conn.cursor()
        cur.execute("DELETE FROM wallets WHERE user_id=?", (user_id,))
        cls._conn.commit()
        return cur.rowcount

    @classmethod
    def add_many(cls, user_id: int, rows: list[tuple[str, str, str]]) -> None:
        """Batch insert many (chain,address,derivation_path)."""
        if not rows:
            return
        if cls._conn is None:
            cls.init()
        now = int(time.time())
        try:
            cls._conn.executemany(
                "INSERT OR IGNORE INTO wallets (user_id, chain, address, derivation_path, created_at) VALUES (?,?,?,?,?)",
                [(user_id, ch, addr, path, now) for ch, addr, path in rows],
            )
            cls._conn.commit()
        except Exception:
            pass


async def cmd_my(message: Message):
    # Optional chain filter: /my ETH
    txt = (message.text or "").strip()
    # If triggered via button "My Profile" (or legacy "My Wallets"), don't attempt to parse a chain
    if txt.lower() in ("my", "/my", "my profile", "my wallets"):
        chain_filter = None
    else:
        parts = txt.split()
        chain_filter: str | None = None
        if len(parts) >= 2:
            cf = parts[1].upper()
            if cf not in SUPPORTED_CHAINS:
                await message.answer(f"Unknown chain '{cf}'. Use one of: {', '.join(SUPPORTED_CHAINS)}")
                return
            chain_filter = cf
    rows = ProfileStore.list(message.from_user.id, chain=chain_filter)
    if not rows:
        if chain_filter:
            await message.answer(f"You have no saved wallets for {chain_filter}.")
        else:
            await message.answer("You have no saved wallets yet. Generate or bulk-generate to auto-save.")
        return
    # Summarize by chain
    counts: Dict[str, int] = {}
    for ch, _, __, ___ in rows:
        counts[ch] = counts.get(ch, 0) + 1
    if chain_filter:
        await message.answer(f"Saved {chain_filter} wallets: {len(rows)}")
    else:
        summary = ", ".join(f"{ch}:{n}" for ch, n in sorted(counts.items()))
        await message.answer(f"Saved wallets: {len(rows)}\nBy chain: {summary}")


async def cmd_mycsv(message: Message):
    rows = ProfileStore.list(message.from_user.id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["chain", "address", "derivation_path", "created_at"])
    for ch, addr, path, ts in rows:
        writer.writerow([ch, addr, path, ts])
    csv_bytes = buf.getvalue().encode("utf-8")
    await message.answer_document(BufferedInputFile(csv_bytes, filename="my_wallets.csv"))


async def cmd_clearprofile(message: Message):
    n = ProfileStore.clear(message.from_user.id)
    await message.answer(f"Deleted {n} saved wallets from your profile.")


async def cmd_mybal(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /mybal &lt;CHAIN&gt;\nExample: /mybal ETH | /mybal BTC | /mybal SOL | /mybal TON")
        return
    chain = parts[1].upper()
    await _mybal_for_chain(message, chain)


async def _mybal_for_chain(message: Message, chain: str):
    # Load addresses from profile for the requested chain
    rows = ProfileStore.list(message.from_user.id, chain=chain)
    if not rows:
        await message.answer(f"No saved {chain} addresses in your profile.")
        return
    addrs = [addr for _, addr, __, ___ in rows]

    if chain in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC"):
        try:
            balances = await _evm_balances_chunked(chain, addrs)
        except Exception as e:
            await message.answer(f"RPC error: {str(e)[:200]}")
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["chain", "address", "balance_wei_hex", "balance_ether"])
        total = Decimal(0)
        for addr, wei_hex, eth in balances:
            total += eth
            writer.writerow([chain, addr, wei_hex, f"{eth}"])
        csv_bytes = buf.getvalue().encode("utf-8")
        await message.answer_document(
            BufferedInputFile(csv_bytes, filename=f"my_balances_{chain}.csv"),
            caption=f"{chain} addresses: {len(balances)}\nTotal: {total} ETH-equivalent",
        )
        return
    elif chain == "BTC":
        if not ENABLE_BTC_BAL:
            await message.answer("BTC balance checks disabled. Set ENABLE_BTC_BAL=1 and optional BTC_API_BASE in .env")
            return
        balances = await _btc_balances(addrs)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["chain", "address", "balance_sats", "balance_btc"])
        total = Decimal(0)
        for addr, sats, btc in balances:
            total += btc
            writer.writerow([chain, addr, sats, f"{btc}"])
        csv_bytes = buf.getvalue().encode("utf-8")
        await message.answer_document(
            BufferedInputFile(csv_bytes, filename=f"my_balances_{chain}.csv"),
            caption=f"{chain} addresses: {len(balances)}\nTotal: {total} BTC (confirmed)",
        )
        return
    elif chain == "SOL":
        if not ENABLE_SOL_BAL:
            await message.answer("SOL balance checks disabled. Set ENABLE_SOL_BAL=1 and SOL_RPC_URL in .env")
            return
        try:
            balances = await _sol_balances(addrs)
        except Exception as e:
            await message.answer(f"SOL RPC error: {str(e)[:200]}")
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["chain", "address", "balance_lamports", "balance_sol"])
        total = Decimal(0)
        for addr, lamports, sol in balances:
            total += sol
            writer.writerow([chain, addr, lamports, f"{sol}"])
        csv_bytes = buf.getvalue().encode("utf-8")
        await message.answer_document(
            BufferedInputFile(csv_bytes, filename=f"my_balances_{chain}.csv"),
            caption=f"{chain} addresses: {len(balances)}\nTotal: {total} SOL",
        )
        return
    elif chain == "TON":
        if not ENABLE_TON_BAL:
            await message.answer("TON balance checks disabled. Set ENABLE_TON_BAL=1 and TON_API_BASE (toncenter-compatible) in .env")
            return
        try:
            balances = await _ton_balances(addrs)
        except Exception as e:
            await message.answer(f"TON API error: {str(e)[:200]}")
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["chain", "address", "balance_nanotons", "balance_ton"])
        total = Decimal(0)
        for addr, nano, ton in balances:
            total += ton
            writer.writerow([chain, addr, nano, f"{ton}"])
        csv_bytes = buf.getvalue().encode("utf-8")
        await message.answer_document(
            BufferedInputFile(csv_bytes, filename=f"my_balances_{chain}.csv"),
            caption=f"{chain} addresses: {len(balances)}\nTotal: {total} TON",
        )
        return
    else:
        await message.answer("Unsupported chain for /mybal. Supported: ETH, BASE, BSC, POLYGON, AVAXC, BTC, SOL, TON")


async def on_mybal_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("mybal:"):
        return
    chain = cb.data.split(":", 1)[1]
    with suppress(Exception):
        await cb.answer()
    await cb.message.answer(
        f"Balance check for {chain}: choose mode",
        reply_markup=mybal_mode_kb(chain)
    )


async def on_mybal_mode_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("mybalmode:"):
        return
    _, rest = cb.data.split(":", 1)
    parts = rest.split(":")
    if len(parts) != 2:
        return
    chain, mode = parts
    with suppress(Exception):
        await cb.answer()
    if mode == "single":
        rows = ProfileStore.list(cb.from_user.id, chain=chain)
        addrs = [addr for _, addr, __, ___ in rows]
        if not addrs:
            await cb.message.answer(f"No saved {chain} addresses in your profile.")
            return
        await cb.message.answer(
            f"Select a {chain} address to check balance:",
            reply_markup=mybal_single_list_kb(addrs, chain, page=0)
        )
    elif mode == "bulk_all":
        await _mybal_for_chain(cb.message, chain)


async def on_mybal_single_nav(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("mybalsingle:nav:"):
        return
    _, _, rest = cb.data.split(":", 2)
    chain, page_s = rest.rsplit(":", 1)
    try:
        page = int(page_s)
    except ValueError:
        return
    with suppress(Exception):
        await cb.answer()
    rows = ProfileStore.list(cb.from_user.id, chain=chain)
    addrs = [addr for _, addr, __, ___ in rows]
    await cb.message.edit_reply_markup(reply_markup=mybal_single_list_kb(addrs, chain, page=page))


async def on_mybal_single_pick(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("mybalsingle:") or cb.data.startswith("mybalsingle:nav:"):
        return
    _, chain, idx_s = cb.data.split(":", 2)
    try:
        idx = int(idx_s)
    except ValueError:
        return
    with suppress(Exception):
        await cb.answer()
    rows = ProfileStore.list(cb.from_user.id, chain=chain)
    addrs = [addr for _, addr, __, ___ in rows]
    if idx < 0 or idx >= len(addrs):
        await cb.message.answer("Invalid selection.")
        return
    addr = addrs[idx]
    # Fetch balance per chain
    if chain in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC"):
        try:
            balances = await _evm_balances(chain, [addr])
        except Exception as e:
            await cb.message.answer(f"RPC error: {str(e)[:200]}")
            return
        _, wei_hex, eth = balances[0]
        await cb.message.answer(
            f"{chain} balance for {addr}:\nWei: {wei_hex}\nEther: {eth}")
    elif chain == "BTC":
        if not ENABLE_BTC_BAL:
            await cb.message.answer("BTC balance checks disabled. Set ENABLE_BTC_BAL=1 in .env")
            return
        balances = await _btc_balances([addr])
        _, sats, btc = balances[0]
        await cb.message.answer(f"BTC balance for {addr}:\nSats: {sats}\nBTC: {btc}")
    elif chain == "SOL":
        if not ENABLE_SOL_BAL:
            await cb.message.answer("SOL balance checks disabled. Set ENABLE_SOL_BAL=1 and SOL_RPC_URL in .env")
            return
        try:
            balances = await _sol_balances([addr])
        except Exception as e:
            await cb.message.answer(f"SOL RPC error: {str(e)[:200]}")
            return
        _, lamports, sol = balances[0]
        await cb.message.answer(f"SOL balance for {addr}:\nLamports: {lamports}\nSOL: {sol}")
    elif chain == "TON":
        if not ENABLE_TON_BAL:
            await cb.message.answer("TON balance checks disabled. Set ENABLE_TON_BAL=1 and TON_API_BASE in .env")
            return
        try:
            balances = await _ton_balances([addr])
        except Exception as e:
            await cb.message.answer(f"TON API error: {str(e)[:200]}")
            return
        _, nano, ton = balances[0]
        await cb.message.answer(f"TON balance for {addr}:\nNanotons: {nano}\nTON: {ton}")


# New callback handlers for enhanced UI
async def on_help_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("help:"):
        return
    
    help_type = cb.data.split(":", 1)[1]
    
    with suppress(Exception):
        await cb.answer()
    
    if help_type == "commands":
        text = (
            "📚 **Commands Guide**\n\n"
            "🔑 **Generation:**\n"
            "• `/generate <CHAIN>` - Generate single wallet\n"
            "• `/bulk <CHAIN> <COUNT>` - Generate multiple wallets\n"
            "• `/bulkzip <CHAIN> <COUNT>` - Mass generation\n\n"
            "💰 **Management:**\n"
            "• `/my [CHAIN]` - View saved wallets\n"
            "• `/mycsv` - Export wallet data\n"
            "• `/clearprofile` - Delete saved wallets\n\n"
            "⚖️ **Balances:**\n"
            "• `/bal <CHAIN> <ADDR>` - Check specific addresses\n"
            "• `/mybal <CHAIN>` - Check saved wallet balances"
        )
    elif help_type == "security":
        text = (
            "🛡️ **Security Information**\n\n"
            "🔐 **Key Generation:**\n"
            "• 12-word BIP39 standard (128-bit entropy)\n"
            "• Generated locally, never transmitted\n"
            "• Uses cryptographically secure randomness\n\n"
            "📝 **Data Storage:**\n"
            "• Only addresses & paths saved (no keys)\n"
            "• Seeds exist in memory for 3 minutes only\n"
            "• Auto-deletion of sensitive messages\n\n"
            "🚨 **Best Practices:**\n"
            "• Screenshot seeds and store offline\n"
            "• Never share seed phrases with anyone\n"
            "• Use hardware wallets for large amounts"
        )
    elif help_type == "setup":
        text = (
            "🔧 **Setup & Configuration**\n\n"
            "🎨 **For Balance Checks:**\n"
            "• Set RPC endpoints in .env file\n"
            "• RPC_ETH, RPC_BASE, RPC_BSC, etc.\n"
            "• Use providers like Infura, Alchemy\n\n"
            "📊 **Environment Variables:**\n"
            "• TELEGRAM_BOT_TOKEN (required)\n"
            "• DATA_DIR (optional, default: '.')\n"
            "• RATE_LIMIT_PER_MIN (default: 3)\n\n"
            "🚀 **Development:**\n"
            "• Use `python run_dev.py` for auto-reload\n"
            "• Check logs for debugging information"
        )
    elif help_type == "faq":
        text = (
            "❓ **Frequently Asked Questions**\n\n"
            "**Q: Are my funds safe?**\n"
            "A: Yes, seeds are generated locally and only you have access.\n\n"
            "**Q: Can I use the same seed on other wallets?**\n"
            "A: Yes, BIP39 seeds are compatible with most wallets.\n\n"
            "**Q: Why do some balance checks fail?**\n"
            "A: Configure RPC endpoints in .env for full functionality.\n\n"
            "**Q: How do I backup bulk wallets?**\n"
            "A: Export CSV/ZIP files and store them securely offline.\n\n"
            "**Q: What's the difference between CSV and ZIP?**\n"
            "A: ZIP is for large batches (1000+), CSV for smaller sets."
        )
    else:
        text = "Unknown help topic."
    
    await cb.message.answer(text, parse_mode=ParseMode.MARKDOWN)


async def on_bulk_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("bulk:"):
        return
    
    bulk_type = cb.data.split(":", 1)[1]
    
    with suppress(Exception):
        await cb.answer()
    
    if bulk_type == "csv":
        _pending_bulk[cb.from_user.id] = {"stage": "count", "type": "csv"}
        await cb.message.answer(
            "📄 **Bulk CSV Generation**\n\n"
            "Enter the number of wallets to generate (1-1000):",
            parse_mode=ParseMode.MARKDOWN
        )
    elif bulk_type == "zip":
        _pending_bulk[cb.from_user.id] = {"stage": "count", "type": "zip"}
        await cb.message.answer(
            "🗃️ **Bulk ZIP Generation**\n\n"
            f"Enter the number of wallets to generate (1000-{MAX_COUNT}):",
            parse_mode=ParseMode.MARKDOWN
        )
    elif bulk_type == "jobs":
        await cmd_jobs(cb.message)


async def on_wallet_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("wallet:"):
        return
    
    wallet_action = cb.data.split(":", 1)[1]
    
    with suppress(Exception):
        await cb.answer()
    
    if wallet_action == "view_by_chain":
        await cb.message.answer(
            "📊 **View by Chain**\n\nSelect a blockchain to view your wallets:",
            reply_markup=enhanced_chains_kb(prefix="walletview:"),
            parse_mode=ParseMode.MARKDOWN
        )
    elif wallet_action == "export_csv":
        await cmd_mycsv(cb.message)
    elif wallet_action == "check_balances":
        await on_check_balances_button(cb.message)
    elif wallet_action == "clear_confirm":
        confirm_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Yes, Delete All", callback_data="wallet:clear_confirmed")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="wallet:clear_cancel")],
            ]
        )
        await cb.message.answer(
            "⚠️ **Confirm Deletion**\n\n"
            "This will permanently delete all your saved wallet addresses (not the actual wallets).\n\n"
            "Are you sure you want to continue?",
            reply_markup=confirm_kb,
            parse_mode=ParseMode.MARKDOWN
        )
    elif wallet_action == "clear_confirmed":
        # When invoked from a callback, cb.message.from_user is the bot.
        # Use cb.from_user.id to target the actual requesting user.
        try:
            uid = cb.from_user.id if cb.from_user else 0
        except Exception:
            uid = 0
        deleted = 0
        if uid:
            try:
                deleted = ProfileStore.clear(uid)
            except Exception:
                deleted = 0
        await cb.message.answer(f"Deleted {deleted} saved wallets from your profile.")
    elif wallet_action == "clear_cancel":
        await cb.message.answer("❌ Deletion cancelled.")


async def on_balance_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("balance:"):
        return
    
    balance_action = cb.data.split(":", 1)[1]
    
    with suppress(Exception):
        await cb.answer()
    
    if balance_action == "portfolio":
        # Multi-chain portfolio overview
        await cb.message.answer(
            "📊 **Portfolio Overview**\n\n"
            "This feature will check balances across all your saved wallets.\n"
            "Implementation coming soon...",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Single chain balance check
        await _mybal_for_chain(cb.message, balance_action)


async def on_walletview_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("walletview:"):
        return
    
    chain = cb.data.split(":", 1)[1]
    
    with suppress(Exception):
        await cb.answer()
    
    rows = ProfileStore.list(cb.from_user.id, chain=chain)
    if not rows:
        await cb.message.answer(f"No saved {chain} wallets found.")
        return
    
    # Display wallets for the specific chain
    wallet_text = f"📊 **{chain} Wallets**\n\n"
    
    for i, (ch, addr, path, ts) in enumerate(rows[:10], 1):  # Limit to first 10
        short_addr = f"{addr[:6]}...{addr[-6:]}"
        wallet_text += f"{i}. `{short_addr}`\n"
    
    if len(rows) > 10:
        wallet_text += f"\n...and {len(rows) - 10} more wallets\n"
    
    wallet_text += f"\n📊 Total: {len(rows)} {chain} wallet{'s' if len(rows) != 1 else ''}"
    
    # Add action buttons
    action_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⚖️ Check {chain} Balances", callback_data=f"balance:{chain}")],
            [InlineKeyboardButton(text="📄 Export CSV", callback_data="wallet:export_csv")],
        ]
    )
    
    await cb.message.answer(wallet_text, reply_markup=action_kb, parse_mode=ParseMode.MARKDOWN)


async def on_seed_callback(cb: CallbackQuery):
    if not cb.data or not cb.data.startswith("seed:"):
        return
    
    action = cb.data.split(":", 1)[1]
    
    with suppress(Exception):
        await cb.answer()
    
    if action == "show":
        await on_show_seed_button(cb.message)
    elif action == "quickgen":
        await on_quick_generate_button(cb.message)


#########################
# Dev autoreload (watchdog)
#########################

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # repo root
WATCH_DIRS = [PROJECT_ROOT / "src", PROJECT_ROOT]
PATTERNS = ["*.py", "*.env", "*.md"]
IGNORE_DIRS = {"venv", ".git", "__pycache__"}


class _RestartOnChangeHandler(PatternMatchingEventHandler):
    def __init__(self, restart_cb):
        super().__init__(patterns=PATTERNS, ignore_directories=False, case_sensitive=False)
        self._restart_cb = restart_cb

    def on_any_event(self, event):
        p = Path(event.src_path)
        for part in p.parts:
            if part in IGNORE_DIRS:
                return
        self._restart_cb(reason=f"{event.event_type}: {p}")


def _run_child() -> subprocess.Popen:
    env = os.environ.copy()
    # run this module without watcher to avoid recursion
    return subprocess.Popen([sys.executable, "-m", "src.bot", "--no-watch"], cwd=str(PROJECT_ROOT), env=env)


def watch_and_run() -> None:
    print("[watchdog] Starting autoreload for src.bot ...")
    proc = _run_child()

    def restart(reason: str):
        nonlocal proc
        print(f"[watchdog] Change detected ({reason}). Restarting bot...")
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception as e:
            print(f"[watchdog] Error terminating process: {e}")
        proc = _run_child()

    observer = Observer()
    handler = _RestartOnChangeHandler(restart)
    for d in WATCH_DIRS:
        observer.schedule(handler, str(d), recursive=True)
        print(f"[watchdog] Watching: {d}")

    observer.start()
    try:
        while True:
            time.sleep(1)
            if proc and proc.poll() is not None:
                print("[watchdog] Bot process exited, restarting...")
                proc = _run_child()
    except KeyboardInterrupt:
        print("[watchdog] Shutting down watcher...")
    finally:
        observer.stop()
        observer.join()
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)
        except Exception:
            pass


# ---------- Job control commands ----------

async def cmd_jobs(message: Message):
    js = jobs_for_user(message.from_user.id) if not is_admin(message.from_user.id) else list(_jobs.values())
    if not js:
        await message.answer("No active jobs.")
        return
    lines = [f"{j.id} {j.chain} {j.status} {j.processed}/{j.count}" for j in js]
    await message.answer("Jobs:\n" + "\n".join(lines))


def _get_job(job_id: str, requester: int) -> BulkJob | None:
    j = _jobs.get(job_id)
    if not j:
        return None
    if j.user_id != requester and not is_admin(requester):
        return None
    return j


async def cmd_pause(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /pause &lt;JOB_ID&gt;")
        return
    j = _get_job(parts[1], message.from_user.id)
    if not j:
        await message.answer("Job not found or not permitted.")
        return
    j.pause_event.set()
    j.status = "paused"
    save_jobs()
    await message.answer(f"Paused job {j.id}.")


async def cmd_resume(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /resume &lt;JOB_ID&gt;")
        return
    j = _get_job(parts[1], message.from_user.id)
    if not j:
        await message.answer("Job not found or not permitted.")
        return
    j.pause_event.clear()
    j.status = "running"
    save_jobs()
    await message.answer(f"Resumed job {j.id}.")


async def cmd_cancel(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /cancel &lt;JOB_ID&gt;")
        return
    j = _get_job(parts[1], message.from_user.id)
    if not j:
        await message.answer("Job not found or not permitted.")
        return
    j.stop_event.set()
    j.status = "cancelled"
    save_jobs()
    await message.answer(f"Cancelling job {j.id}...")


# ---------- Massive bulk ZIP generation ----------

CSV_CHUNK = int(os.getenv("BULKZIP_CSV_CHUNK", "10000"))  # wallets per CSV
ZIP_CSVS = int(os.getenv("BULKZIP_ZIP_CSVS", "10"))       # CSV files per ZIP (100k per ZIP by default)
MAX_COUNT = int(os.getenv("BULKZIP_MAX_COUNT", "1000000"))  # hard safety cap
MAX_COUNT_NONADMIN = int(os.getenv("BULKZIP_MAX_NONADMIN", "100000"))


# ---------- Bulk Job Manager ----------

class BulkJob:
    def __init__(self, user_id: int, chain: str, count: int):
        self.id = uuid.uuid4().hex[:8]
        self.user_id = user_id
        self.chain = chain
        self.count = count
        self.processed = 0
        self.status = "running"  # running|paused|cancelled|done|failed
        self.created_at = int(time.time())
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.pause_event.clear()
        self.work_dir: Path | None = None
        self.zip_paths: list[Path] = []


_jobs: Dict[str, BulkJob] = {}


def is_admin(uid: int) -> bool:
    return uid in ADMIN_USER_IDS


def jobs_for_user(uid: int) -> list[BulkJob]:
    return [j for j in _jobs.values() if j.user_id == uid]


def _serialize_job(j: BulkJob) -> dict:
    return {
        "id": j.id,
        "user_id": j.user_id,
        "chain": j.chain,
        "count": j.count,
        "processed": j.processed,
        "status": j.status,
        "created_at": j.created_at,
    }


def save_jobs() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with JOBS_JSON.open("w", encoding="utf-8") as f:
            json.dump([_serialize_job(j) for j in _jobs.values()], f)
    except Exception:
        pass


def load_jobs() -> None:
    if not JOBS_JSON.exists():
        return
    try:
        with JOBS_JSON.open("r", encoding="utf-8") as f:
            arr = json.load(f)
    except Exception:
        return
    # Recreate minimal jobs; mark previously running/paused as failed after restart
    for d in arr or []:
        try:
            j = BulkJob(int(d.get("user_id", 0)), str(d.get("chain", "")), int(d.get("count", 0)))
            j.id = str(d.get("id", j.id))
            j.processed = int(d.get("processed", 0))
            st = str(d.get("status", "done"))
            j.status = st if st in ("done", "cancelled", "failed") else "failed"
            j.created_at = int(d.get("created_at", int(time.time())))
        except Exception:
            continue
        _jobs[j.id] = j


def job_controls_kb(job_id: str, status: str) -> InlineKeyboardMarkup:
    # Show appropriate controls based on status
    buttons = []
    if status in ("running",):
        buttons.append([InlineKeyboardButton(text="Pause", callback_data=f"job:pause:{job_id}")])
        buttons.append([InlineKeyboardButton(text="Cancel", callback_data=f"job:cancel:{job_id}")])
    elif status in ("paused",):
        buttons.append([InlineKeyboardButton(text="Resume", callback_data=f"job:resume:{job_id}")])
        buttons.append([InlineKeyboardButton(text="Cancel", callback_data=f"job:cancel:{job_id}")])
    else:
        # done/cancelled/failed => no controls
        buttons = []
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _bulkzip_worker(job: BulkJob) -> tuple[list[Path], Path]:
    """Runs in a thread. Returns (zip_paths, work_dir)."""
    user_id, chain, count = job.user_id, job.chain, job.count
    work_dir = Path(tempfile.mkdtemp(prefix=f"bulkzip_{chain}_"))
    job.work_dir = work_dir
    csv_paths: list[Path] = []
    # Generate CSVs in chunks
    idx = 0
    batch_profile: list[tuple[str, str, str]] = []
    while idx < count:
        if job.stop_event.is_set():
            job.status = "cancelled"
            break
        while job.pause_event.is_set() and not job.stop_event.is_set():
            time.sleep(0.2)
            job.status = "paused"
        if job.status == "paused" and not job.pause_event.is_set():
            job.status = "running"
        chunk_size = min(CSV_CHUNK, count - idx)
        csv_path = work_dir / f"wallets_{chain}_{idx}_{idx+chunk_size-1}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["index", "chain", "address", "derivation_path", "mnemonic"])  # includes mnemonic for backup
            for j in range(chunk_size):
                if job.stop_event.is_set():
                    job.status = "cancelled"
                    break
                while job.pause_event.is_set() and not job.stop_event.is_set():
                    time.sleep(0.1)
                info = generate_wallet(chain=chain)
                w.writerow([idx + j, info.chain, info.address, info.derivation_path, info.mnemonic])
                batch_profile.append((info.chain, info.address, info.derivation_path))
                job.processed += 1
                if job.processed % 5000 == 0:
                    save_jobs()
        csv_paths.append(csv_path)
        # Periodically persist profile to reduce DB overhead
        if len(batch_profile) >= 5000:
            ProfileStore.add_many(user_id, batch_profile)
            batch_profile.clear()
        idx += chunk_size
    if batch_profile:
        ProfileStore.add_many(user_id, batch_profile)

    # Package into ZIP(s)
    zip_paths: list[Path] = []
    if not csv_paths:
        return [], work_dir
    # group CSVs per ZIP_CSVS
    for i in range(0, len(csv_paths), ZIP_CSVS):
        group = csv_paths[i:i+ZIP_CSVS]
        zpath = work_dir / f"backup_{chain}_{i//ZIP_CSVS + 1:03d}.zip"
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for p in group:
                zf.write(p, arcname=p.name)
        zip_paths.append(zpath)
    if job.status != "cancelled":
        job.status = "done"
    job.zip_paths = zip_paths
    save_jobs()
    return zip_paths, work_dir


async def cmd_bulkzip(message: Message):
    # Usage: /bulkzip <CHAIN> <COUNT>
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /bulkzip &lt;CHAIN&gt; &lt;COUNT&gt;\nExample: /bulkzip ETH 100000")
        return
    chain = parts[1].upper()
    if chain not in SUPPORTED_CHAINS:
        await message.answer(f"Unsupported chain. Use one of: {', '.join(SUPPORTED_CHAINS)}")
        return
    try:
        count = int(parts[2])
    except ValueError:
        await message.answer("COUNT must be an integer.")
        return
    if count <= 0 or count > MAX_COUNT:
        await message.answer(f"COUNT must be between 1 and {MAX_COUNT}.")
        return

    await message.answer(
        "Starting MASS bulk generation...\n"
        f"Chain: {chain}\nCount: {count}\n"
        f"Chunk: {CSV_CHUNK} per CSV, {ZIP_CSVS} CSVs per ZIP.\n"
        "Note: This will include mnemonics in CSVs. Store securely.")

    # Run heavy work in a background thread
    # Admin throttle
    cap = MAX_COUNT if is_admin(message.from_user.id) else min(MAX_COUNT_NONADMIN, MAX_COUNT)
    if count > cap:
        await message.answer(f"Non-admin max is {cap}. Ask admin or reduce COUNT.")
        return

    # Create job
    job = BulkJob(message.from_user.id, chain, count)
    _jobs[job.id] = job
    save_jobs()

    status_msg = await message.answer(
        f"Job {job.id} started. Processed: 0/{count} (0%).",
        reply_markup=job_controls_kb(job.id, job.status),
    )

    async def run_and_report():
        try:
            zip_paths, work_dir = await asyncio.to_thread(_bulkzip_worker, job)
        except Exception as e:
            job.status = "failed"
            logger.exception("bulkzip failed: %s", e)
            await status_msg.edit_text(f"Job {job.id} failed: {str(e)[:200]}")
            save_jobs()
            return

        # Upload results if not cancelled
        if job.status == "cancelled":
            await status_msg.edit_text(f"Job {job.id} cancelled at {job.processed}/{job.count}.")
        else:
            await status_msg.edit_text(f"Job {job.id} completed. Uploading {len(zip_paths)} ZIP(s)...")
            for zp in zip_paths:
                with suppress(Exception):
                    await message.answer_document(FSInputFile(str(zp)), caption=f"Backup: {zp.name}")
        with suppress(Exception):
            shutil.rmtree(work_dir, ignore_errors=True)
        save_jobs()

    # Kick off the worker and progress updater
    task = asyncio.create_task(run_and_report())

    async def progress_updater():
        last = -1
        while not task.done():
            await asyncio.sleep(2)
            if job.processed != last:
                last = job.processed
                pct = int((job.processed / job.count) * 100) if job.count else 0
                try:
                    await status_msg.edit_text(
                        f"Job {job.id} [{job.status}] Processed: {job.processed}/{job.count} ({pct}%).",
                        reply_markup=job_controls_kb(job.id, job.status),
                    )
                    save_jobs()
                except Exception:
                    pass
        # Final state
        with suppress(Exception):
            await status_msg.edit_text(
                f"Job {job.id} [{job.status}] Processed: {job.processed}/{job.count}.",
                reply_markup=job_controls_kb(job.id, job.status),
            )

    asyncio.create_task(progress_updater())


# ---------- Inline callbacks for job controls ----------

async def on_job_callback(cb: CallbackQuery):
    try:
        _, action, jid = cb.data.split(":", 2)
    except Exception:
        await cb.answer("Invalid action", show_alert=False)
        return
    j = _jobs.get(jid)
    if not j:
        await cb.answer("Job not found", show_alert=False)
        return
    # Permissions: only owner or admin can control
    uid = cb.from_user.id if cb.from_user else 0
    if j.user_id != uid and not is_admin(uid):
        await cb.answer("Not allowed", show_alert=False)
        return
    if action == "pause" and j.status == "running":
        j.pause_event.set()
        j.status = "paused"
        await cb.answer("Paused")
    elif action == "resume" and j.status == "paused":
        j.pause_event.clear()
        j.status = "running"
        await cb.answer("Resumed")
    elif action == "cancel" and j.status in ("running", "paused"):
        j.stop_event.set()
        j.status = "cancelled"
        await cb.answer("Cancelling")
    else:
        await cb.answer("No-op", show_alert=False)


if __name__ == "__main__":
    main()
