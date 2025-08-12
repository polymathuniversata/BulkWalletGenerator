"""
Input validation and sanitization utilities for the Wallet Bot.

This module provides comprehensive validation for user inputs to prevent
security issues, improve error handling, and enhance user experience.
"""
from __future__ import annotations

import re
from typing import Optional, Union, List, Tuple
from decimal import Decimal, InvalidOperation

from .wallets import Chain

# Import SUPPORTED_CHAINS from bot.py to avoid circular imports
SUPPORTED_CHAINS = (
    "ETH", "BTC", "SOL", "BASE", "BSC", "POLYGON", "AVAXC", "TRON", "XRP", "DOGE", "LTC", "TON"
)

# Regular expressions for various input types
PATTERNS = {
    'ethereum_address': re.compile(r'^0x[a-fA-F0-9]{40}$'),
    'bitcoin_address': re.compile(r'^(bc1|[13])[a-zA-Z0-9]{25,62}$'),
    'solana_address': re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$'),
    'tron_address': re.compile(r'^T[A-Za-z0-9]{33}$'),
    'xrp_address': re.compile(r'^r[1-9A-HJ-NP-Za-km-z]{25,34}$'),
    'litecoin_address': re.compile(r'^(ltc1|[LM])[a-zA-Z0-9]{25,62}$'),
    'dogecoin_address': re.compile(r'^D[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}$'),
    'ton_address': re.compile(r'^[0-9a-fA-F]{64}$|^[A-Za-z0-9_-]{48}$'),
    'telegram_user_id': re.compile(r'^[1-9][0-9]{1,15}$'),
    'positive_integer': re.compile(r'^[1-9][0-9]*$'),
    'chain_name': re.compile(r'^[A-Z]{2,10}$'),
    'filename_safe': re.compile(r'^[a-zA-Z0-9._-]+$'),
    'hex_string': re.compile(r'^0x[a-fA-F0-9]+$'),
}

# Maximum input lengths for security
MAX_LENGTHS = {
    'text_input': 1000,
    'address': 100,
    'filename': 255,
    'bulk_count': 10,  # characters, not count value
    'chain_name': 10,
    'callback_data': 64,
}

class ValidationError(Exception):
    """Raised when input validation fails."""
    def __init__(self, message: str, field: str = "", value: str = ""):
        super().__init__(message)
        self.field = field
        self.value = value
        self.message = message

class InputValidator:
    """Comprehensive input validation and sanitization."""
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = MAX_LENGTHS['text_input']) -> str:
        """Sanitize general text input."""
        if not isinstance(text, str):
            raise ValidationError("Input must be a string")
        
        # Strip whitespace and limit length
        sanitized = text.strip()[:max_length]
        
        # Remove potentially dangerous characters
        # Allow alphanumeric, spaces, and safe punctuation
        sanitized = re.sub(r'[^\w\s.,!?@#$%^&*()[\]{};:"\'-+=<>/\\|`~]', '', sanitized)
        
        return sanitized
    
    @staticmethod
    def validate_chain(chain: str) -> Chain:
        """Validate and normalize blockchain chain name."""
        if not isinstance(chain, str):
            raise ValidationError("Chain must be a string", field="chain")
        
        chain_upper = chain.upper().strip()
        
        if not PATTERNS['chain_name'].match(chain_upper):
            raise ValidationError(
                "Invalid chain format. Must be 2-10 uppercase letters.",
                field="chain", 
                value=chain
            )
        
        if chain_upper not in SUPPORTED_CHAINS:
            raise ValidationError(
                f"Unsupported chain. Supported chains: {', '.join(SUPPORTED_CHAINS)}",
                field="chain",
                value=chain
            )
        
        return chain_upper  # type: ignore
    
    @staticmethod
    def validate_bulk_count(count_str: str, min_count: int = 1, max_count: int = 1000) -> int:
        """Validate bulk generation count."""
        if not isinstance(count_str, str):
            raise ValidationError("Count must be provided as a string", field="count")
        
        count_str = count_str.strip()
        
        if len(count_str) > MAX_LENGTHS['bulk_count']:
            raise ValidationError("Count input too long", field="count", value=count_str)
        
        if not PATTERNS['positive_integer'].match(count_str):
            raise ValidationError(
                "Count must be a positive integer",
                field="count",
                value=count_str
            )
        
        try:
            count = int(count_str)
        except ValueError:
            raise ValidationError("Invalid number format", field="count", value=count_str)
        
        if not (min_count <= count <= max_count):
            raise ValidationError(
                f"Count must be between {min_count:,} and {max_count:,}",
                field="count",
                value=str(count)
            )
        
        return count
    
    @staticmethod
    def validate_address(address: str, chain: Optional[Chain] = None) -> str:
        """Validate blockchain address format."""
        if not isinstance(address, str):
            raise ValidationError("Address must be a string", field="address")
        
        address = address.strip()
        
        if len(address) > MAX_LENGTHS['address']:
            raise ValidationError("Address too long", field="address", value=address[:50] + "...")
        
        if not address:
            raise ValidationError("Address cannot be empty", field="address")
        
        # Chain-specific validation
        if chain:
            valid = False
            if chain in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC"):
                valid = bool(PATTERNS['ethereum_address'].match(address))
            elif chain == "BTC":
                valid = bool(PATTERNS['bitcoin_address'].match(address))
            elif chain == "SOL":
                valid = bool(PATTERNS['solana_address'].match(address))
            elif chain == "TRON":
                valid = bool(PATTERNS['tron_address'].match(address))
            elif chain == "XRP":
                valid = bool(PATTERNS['xrp_address'].match(address))
            elif chain == "LTC":
                valid = bool(PATTERNS['litecoin_address'].match(address))
            elif chain == "DOGE":
                valid = bool(PATTERNS['dogecoin_address'].match(address))
            elif chain == "TON":
                valid = bool(PATTERNS['ton_address'].match(address))
            
            if not valid:
                raise ValidationError(
                    f"Invalid {chain} address format",
                    field="address",
                    value=address
                )
        
        return address
    
    @staticmethod
    def validate_addresses_list(addresses_text: str, chain: Chain) -> List[str]:
        """Validate a list of addresses from text input."""
        if not isinstance(addresses_text, str):
            raise ValidationError("Addresses must be provided as text", field="addresses")
        
        addresses_text = addresses_text.strip()
        if not addresses_text:
            raise ValidationError("No addresses provided", field="addresses")
        
        # Split by common delimiters
        addresses = re.split(r'[,\s\n]+', addresses_text)
        addresses = [addr.strip() for addr in addresses if addr.strip()]
        
        if not addresses:
            raise ValidationError("No valid addresses found", field="addresses")
        
        if len(addresses) > 1000:  # Reasonable limit
            raise ValidationError("Too many addresses (max 1000)", field="addresses")
        
        validated_addresses = []
        for i, addr in enumerate(addresses):
            try:
                validated_addr = InputValidator.validate_address(addr, chain)
                validated_addresses.append(validated_addr)
            except ValidationError as e:
                raise ValidationError(
                    f"Address {i+1} invalid: {e.message}",
                    field="addresses",
                    value=addr
                )
        
        return validated_addresses
    
    @staticmethod
    def validate_telegram_user_id(user_id: Union[str, int]) -> int:
        """Validate Telegram user ID."""
        if isinstance(user_id, int):
            user_id_str = str(user_id)
        elif isinstance(user_id, str):
            user_id_str = user_id.strip()
        else:
            raise ValidationError("User ID must be a string or integer", field="user_id")
        
        if not PATTERNS['telegram_user_id'].match(user_id_str):
            raise ValidationError(
                "Invalid Telegram user ID format",
                field="user_id",
                value=user_id_str
            )
        
        try:
            return int(user_id_str)
        except ValueError:
            raise ValidationError("Invalid user ID number", field="user_id", value=user_id_str)
    
    @staticmethod
    def validate_filename(filename: str) -> str:
        """Validate filename for security."""
        if not isinstance(filename, str):
            raise ValidationError("Filename must be a string", field="filename")
        
        filename = filename.strip()
        
        if len(filename) > MAX_LENGTHS['filename']:
            raise ValidationError("Filename too long", field="filename")
        
        if not filename:
            raise ValidationError("Filename cannot be empty", field="filename")
        
        # Check for directory traversal attempts
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValidationError("Invalid filename - contains path separators", field="filename")
        
        if not PATTERNS['filename_safe'].match(filename):
            raise ValidationError(
                "Filename contains invalid characters",
                field="filename",
                value=filename
            )
        
        return filename
    
    @staticmethod
    def validate_callback_data(data: str) -> str:
        """Validate callback data from inline keyboards."""
        if not isinstance(data, str):
            raise ValidationError("Callback data must be a string", field="callback_data")
        
        data = data.strip()
        
        if len(data) > MAX_LENGTHS['callback_data']:
            raise ValidationError("Callback data too long", field="callback_data")
        
        if not data:
            raise ValidationError("Callback data cannot be empty", field="callback_data")
        
        # Allow alphanumeric, colons, underscores, hyphens
        if not re.match(r'^[a-zA-Z0-9:_-]+$', data):
            raise ValidationError(
                "Invalid callback data format",
                field="callback_data",
                value=data
            )
        
        return data
    
    @staticmethod
    def validate_hex_string(hex_str: str) -> str:
        """Validate hexadecimal string (for balance values, etc.)."""
        if not isinstance(hex_str, str):
            raise ValidationError("Hex string must be a string", field="hex")
        
        hex_str = hex_str.strip()
        
        if not PATTERNS['hex_string'].match(hex_str):
            raise ValidationError(
                "Invalid hexadecimal format",
                field="hex",
                value=hex_str
            )
        
        return hex_str
    
    @staticmethod
    def sanitize_for_display(text: str, max_length: int = 100) -> str:
        """Sanitize text for safe display in messages."""
        if not isinstance(text, str):
            return str(text)[:max_length]
        
        # Remove or escape potentially dangerous characters
        sanitized = text.replace('<', '&lt;').replace('>', '&gt;')
        sanitized = sanitized.replace('&', '&amp;').replace('"', '&quot;')
        
        return sanitized[:max_length]


def validate_user_input(validator_func):
    """Decorator to validate user input and provide consistent error handling."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ValidationError as e:
                # Extract message object from args (typically first arg for handlers)
                message = args[0] if args else None
                if hasattr(message, 'answer'):
                    error_msg = f"❌ **Input Error**\n\n{e.message}"
                    if e.field:
                        error_msg += f"\nField: {e.field}"
                    await message.answer(error_msg, parse_mode="Markdown")
                    return None
                else:
                    raise
            except Exception as e:
                # Handle unexpected errors gracefully
                message = args[0] if args else None
                if hasattr(message, 'answer'):
                    await message.answer(
                        "❌ **Unexpected Error**\n\nPlease try again or contact support if the issue persists.",
                        parse_mode="Markdown"
                    )
                    return None
                else:
                    raise
        return wrapper
    return decorator

# Convenience functions for common validations
def safe_chain(chain: str) -> Chain:
    """Quick chain validation."""
    return InputValidator.validate_chain(chain)

def safe_count(count_str: str, max_count: int = 1000) -> int:
    """Quick count validation."""
    return InputValidator.validate_bulk_count(count_str, max_count=max_count)

def safe_address(address: str, chain: Optional[Chain] = None) -> str:
    """Quick address validation."""
    return InputValidator.validate_address(address, chain)