"""
Wallet generation and seed management handlers.
"""
import asyncio
from contextlib import suppress
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

from ..wallets import generate_wallet, address_qr_png
from ..validators import safe_chain, ValidationError
from ..error_handling import with_error_handling, safe_answer_callback
from ..services.wallet_service import WalletService
from ..services.profile_service import ProfileService
from ..utils.rate_limiter import RateLimiter

# Initialize services
wallet_service = WalletService()
profile_service = ProfileService()
rate_limiter = RateLimiter()

@with_error_handling(context="cmd_generate", user_message="Failed to generate wallet")
async def cmd_generate(message: Message):
    """Handle /generate command."""
    if rate_limiter.is_rate_limited(message.from_user.id):
        await message.answer("⏰ Rate limit exceeded. Please wait a minute before generating another wallet.")
        return

    if not message.text:
        await message.answer("❌ No command text received. Please try again.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "📝 **Usage**: `/generate <CHAIN>`\\n\\n"
            "**Example**: `/generate ETH`\\n\\n"
            "**Supported chains**: ETH, BTC, SOL, BASE, BSC, POLYGON, AVAXC, TRON, XRP, DOGE, LTC, TON",
            parse_mode="Markdown"
        )
        return

    try:
        chain = safe_chain(parts[1])
    except ValidationError as e:
        await message.answer(f"❌ {e.message}")
        return

    await do_generate(message, chain)

@with_error_handling(context="do_generate", user_message="Failed to generate wallet")
async def do_generate(message: Message, chain: str):
    """Core wallet generation logic."""
    try:
        # Generate wallet using service
        wallet_info = await wallet_service.generate_wallet(chain, message.from_user.id)
        
        # Get balance if possible
        balance_line = await wallet_service.get_live_balance(chain, wallet_info.address)
        
        # Format response message
        text = (
            f"Chain: {wallet_info.chain}\\n"
            f"Address: `{wallet_info.address}`\\n"
            f"Path: `{wallet_info.derivation_path}`\\n"
            f"{balance_line}"
            "\\nTap the QR image to save. Use 'Show Seed' to reveal the seed once."
        )
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

        # Send QR code
        qr_data = address_qr_png(wallet_info.address)
        await message.answer_photo(
            BufferedInputFile(qr_data.read(), filename=f"{wallet_info.chain}_address.png"), 
            caption=f"{wallet_info.chain} address QR"
        )

        # Save to profile (non-sensitive data only)
        await profile_service.add_wallet(
            message.from_user.id, 
            wallet_info.chain, 
            wallet_info.address, 
            wallet_info.derivation_path
        )

        # Store seed temporarily
        wallet_service.store_seed_temporarily(message.from_user.id, wallet_info.mnemonic)
        
        # Enhanced seed reveal options
        seed_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔑 Show Seed Phrase", callback_data="seed:show")],
                [InlineKeyboardButton(text="📄 Generate Another", callback_data="gen:quickgen")],
            ]
        )
        
        await message.answer(
            "✅ **Wallet Generated Successfully!**\\n\\n"
            "🔑 Your seed phrase is ready (expires in 3 minutes)\\n"
            "💾 Address automatically saved to your profile\\n\\n"
            "💡 **Next Steps:**\\n"
            "• Reveal your seed phrase to back it up\\n"
            "• Generate more wallets if needed",
            reply_markup=seed_kb,
            parse_mode=ParseMode.MARKDOWN
        )

    except ValidationError as e:
        await message.answer(f"❌ {e.message}")
        return
    except Exception as e:
        await message.answer("❌ Failed to generate wallet. Please try again.")
        return

@with_error_handling(context="generate_callback")
async def on_generate_callback(cb: CallbackQuery):
    """Handle chain selection callback."""
    if not cb.data or not cb.data.startswith("gen:"):
        return
    
    try:
        from ..validators import InputValidator
        callback_data = InputValidator.validate_callback_data(cb.data)
        chain = safe_chain(callback_data.split(":", 1)[1])
    except (ValidationError, IndexError):
        await safe_answer_callback(cb, "Invalid selection", show_alert=True)
        return
    
    await safe_answer_callback(cb)
    await do_generate(cb.message, chain)

async def cmd_showseed(message: Message):
    """Handle /showseed command."""
    # Enhanced seed reveal with better UX
    mnemonic = wallet_service.get_stored_seed(message.from_user.id)
    if not mnemonic:
        await message.answer(
            "🔑 **Show Seed**\\n\\n"
            "📭 No seed available to show.\\n\\n"
            "Seeds are only available for 3 minutes after generation. Generate a new wallet to get a fresh seed.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Send seed with enhanced formatting and security warning
    sent = await message.answer(
        "🔑 **Your 12-Word Seed Phrase**\\n\\n"
        f"📝 `{mnemonic}`\\n\\n"
        "⚠️ **SECURITY WARNING:**\\n"
        "• This message will auto-delete in 30 seconds\\n"
        "• Screenshot and store offline securely\\n"
        "• Never share or send to anyone\\n"
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

async def cmd_delete(message: Message):
    """Handle /delete command."""
    if message.reply_to_message:
        with suppress(Exception):
            await message.reply_to_message.delete()
        await message.answer("Deleted.")
    else:
        await message.answer("Reply to the message you want to delete and send /delete.")

async def on_seed_callback(cb: CallbackQuery):
    """Handle seed-related callbacks."""
    if not cb.data or not cb.data.startswith("seed:"):
        return
    
    action = cb.data.split(":", 1)[1]
    
    await safe_answer_callback(cb)
    
    if action == "show":
        await cmd_showseed(cb.message)
    elif action == "quickgen":
        from .ui_handlers import on_quick_generate_button
        await on_quick_generate_button(cb.message)