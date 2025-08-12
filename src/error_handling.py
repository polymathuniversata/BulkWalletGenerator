"""
Comprehensive error handling utilities for the Wallet Bot.

This module provides decorators, middleware, and utilities for robust
error handling across all async operations in the bot.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import suppress
from functools import wraps
from typing import Any, Callable, Optional, Union, Dict
from datetime import datetime

import aiohttp
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import (
    TelegramAPIError, 
    TelegramNetworkError, 
    TelegramRetryAfter,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramConflictError
)

logger = logging.getLogger(__name__)

class ErrorHandler:
    """Centralized error handling for the bot."""
    
    # Track error frequency to detect issues
    error_counts: Dict[str, int] = {}
    last_error_report = datetime.now()
    
    @staticmethod
    def log_error(error: Exception, context: str = "", user_id: Optional[int] = None) -> None:
        """Log errors with context and user information."""
        error_type = type(error).__name__
        ErrorHandler.error_counts[error_type] = ErrorHandler.error_counts.get(error_type, 0) + 1
        
        logger.error(
            "Error in %s: %s (User: %s) - %s", 
            context, 
            error_type, 
            user_id or "unknown",
            str(error),
            exc_info=True
        )
    
    @staticmethod
    async def send_user_error(
        message_handler: Union[Message, CallbackQuery], 
        error_message: str,
        show_retry: bool = True
    ) -> None:
        """Send user-friendly error message."""
        try:
            retry_text = "\n\n🔄 Please try again in a moment." if show_retry else ""
            full_message = f"❌ **Error**\n\n{error_message}{retry_text}"
            
            if isinstance(message_handler, CallbackQuery):
                await message_handler.message.answer(full_message, parse_mode="Markdown")
                with suppress(Exception):
                    await message_handler.answer("Error occurred", show_alert=False)
            else:
                await message_handler.answer(full_message, parse_mode="Markdown")
                
        except Exception as e:
            logger.error("Failed to send error message to user: %s", e)
    
    @staticmethod
    def should_retry(error: Exception, attempt: int, max_retries: int = 3) -> bool:
        """Determine if an operation should be retried."""
        if attempt >= max_retries:
            return False
        
        # Retry on network issues
        if isinstance(error, (aiohttp.ClientError, TelegramNetworkError, asyncio.TimeoutError)):
            return True
        
        # Retry on temporary Telegram API issues
        if isinstance(error, TelegramRetryAfter):
            return True
        
        # Don't retry on user errors or permanent failures
        if isinstance(error, (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound)):
            return False
            
        return False


def with_error_handling(
    context: str = "",
    user_message: Optional[str] = None,
    retry_count: int = 3,
    silence_errors: bool = False
):
    """Decorator for comprehensive async error handling."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            attempt = 0
            last_error = None
            
            # Extract user info for logging
            user_id = None
            message_handler = None
            
            for arg in args:
                if isinstance(arg, (Message, CallbackQuery)):
                    message_handler = arg
                    if hasattr(arg, 'from_user') and arg.from_user:
                        user_id = arg.from_user.id
                    elif hasattr(arg, 'message') and arg.message and arg.message.from_user:
                        user_id = arg.message.from_user.id
                    break
            
            while attempt < retry_count:
                try:
                    return await func(*args, **kwargs)
                    
                except TelegramRetryAfter as e:
                    # Handle rate limiting with proper backoff
                    wait_time = min(e.retry_after, 300)  # Max 5 minutes
                    logger.warning(
                        "Rate limited in %s (User: %s). Waiting %d seconds.",
                        context or func.__name__,
                        user_id,
                        wait_time
                    )
                    await asyncio.sleep(wait_time)
                    attempt += 1
                    last_error = e
                    continue
                    
                except TelegramNetworkError as e:
                    # Network issues - retry with exponential backoff
                    if attempt < retry_count - 1:
                        wait_time = (2 ** attempt) * 1.0  # 1s, 2s, 4s, etc.
                        logger.warning(
                            "Network error in %s (attempt %d/%d). Retrying in %.1fs...",
                            context or func.__name__,
                            attempt + 1,
                            retry_count,
                            wait_time
                        )
                        await asyncio.sleep(wait_time)
                        attempt += 1
                        last_error = e
                        continue
                    else:
                        last_error = e
                        break
                        
                except TelegramBadRequest as e:
                    # User/client errors - don't retry
                    logger.warning(
                        "Bad request in %s (User: %s): %s",
                        context or func.__name__,
                        user_id,
                        str(e)
                    )
                    if not silence_errors and message_handler:
                        await ErrorHandler.send_user_error(
                            message_handler,
                            "Invalid request. Please check your input and try again.",
                            show_retry=False
                        )
                    return None
                    
                except TelegramForbiddenError as e:
                    # Bot blocked or insufficient permissions
                    logger.warning(
                        "Forbidden in %s (User: %s): Bot blocked or insufficient permissions",
                        context or func.__name__,
                        user_id
                    )
                    return None  # Silently fail for blocked users
                    
                except aiohttp.ClientError as e:
                    # External API errors (RPC, etc.)
                    if attempt < retry_count - 1:
                        wait_time = (2 ** attempt) * 1.0
                        logger.warning(
                            "API error in %s (attempt %d/%d): %s",
                            context or func.__name__,
                            attempt + 1,
                            retry_count,
                            str(e)
                        )
                        await asyncio.sleep(wait_time)
                        attempt += 1
                        last_error = e
                        continue
                    else:
                        last_error = e
                        break
                        
                except asyncio.TimeoutError as e:
                    # Timeout errors
                    if attempt < retry_count - 1:
                        logger.warning(
                            "Timeout in %s (attempt %d/%d)",
                            context or func.__name__,
                            attempt + 1,
                            retry_count
                        )
                        attempt += 1
                        last_error = e
                        continue
                    else:
                        last_error = e
                        break
                        
                except Exception as e:
                    # Unexpected errors
                    ErrorHandler.log_error(e, context or func.__name__, user_id)
                    
                    if not silence_errors and message_handler:
                        error_msg = user_message or "An unexpected error occurred. Please try again."
                        await ErrorHandler.send_user_error(message_handler, error_msg)
                    
                    # Don't retry on unexpected errors unless explicitly requested
                    return None
            
            # All retries exhausted
            if last_error:
                ErrorHandler.log_error(last_error, context or func.__name__, user_id)
                
                if not silence_errors and message_handler:
                    if isinstance(last_error, (TelegramNetworkError, aiohttp.ClientError, asyncio.TimeoutError)):
                        error_msg = "Network or service temporarily unavailable. Please try again later."
                    else:
                        error_msg = user_message or "Operation failed after multiple attempts. Please try again later."
                    
                    await ErrorHandler.send_user_error(message_handler, error_msg)
            
            return None
            
        return wrapper
    return decorator


def with_fallback(fallback_func: Optional[Callable] = None, fallback_value: Any = None):
    """Decorator to provide fallback behavior on errors."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.warning("Function %s failed, using fallback: %s", func.__name__, str(e))
                
                if fallback_func:
                    try:
                        if asyncio.iscoroutinefunction(fallback_func):
                            return await fallback_func(*args, **kwargs)
                        else:
                            return fallback_func(*args, **kwargs)
                    except Exception as fallback_error:
                        logger.error("Fallback function also failed: %s", fallback_error)
                        return fallback_value
                
                return fallback_value
                
        return wrapper
    return decorator


def safe_async(func: Callable) -> Callable:
    """Simple decorator for basic async safety."""
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error("Safe async error in %s: %s", func.__name__, str(e))
            return None
    return wrapper


class RateLimitHandler:
    """Handle rate limiting with proper backoff and user feedback."""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    async def handle_rate_limit(
        self, 
        func: Callable, 
        message_handler: Union[Message, CallbackQuery],
        *args, 
        **kwargs
    ) -> Any:
        """Execute function with rate limit handling."""
        attempt = 0
        
        while attempt < self.max_retries:
            try:
                return await func(*args, **kwargs)
                
            except TelegramRetryAfter as e:
                attempt += 1
                wait_time = min(e.retry_after, 300)  # Cap at 5 minutes
                
                if attempt < self.max_retries:
                    # Inform user about the delay
                    await ErrorHandler.send_user_error(
                        message_handler,
                        f"⏳ Rate limited. Retrying in {wait_time} seconds... (Attempt {attempt}/{self.max_retries})",
                        show_retry=False
                    )
                    await asyncio.sleep(wait_time)
                else:
                    await ErrorHandler.send_user_error(
                        message_handler,
                        "❌ Service temporarily overloaded. Please try again in a few minutes.",
                        show_retry=False
                    )
                    return None
                    
        return None


# Context managers for error handling
class ErrorContext:
    """Context manager for error handling in specific operations."""
    
    def __init__(
        self, 
        context_name: str, 
        user_id: Optional[int] = None,
        silence_errors: bool = False
    ):
        self.context_name = context_name
        self.user_id = user_id
        self.silence_errors = silence_errors
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            ErrorHandler.log_error(exc_val, self.context_name, self.user_id)
            
            if not self.silence_errors:
                # Could send error notifications here if needed
                pass
        
        # Return None to re-raise the exception
        return None


# Utility functions for common error patterns
async def safe_delete_message(message: Message, delay: float = 0) -> bool:
    """Safely delete a message with optional delay."""
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await message.delete()
        return True
    except Exception as e:
        logger.debug("Failed to delete message: %s", e)
        return False

async def safe_edit_message(
    message: Message, 
    text: str, 
    **kwargs
) -> bool:
    """Safely edit a message with error handling."""
    try:
        await message.edit_text(text, **kwargs)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True  # Message unchanged, not an error
        logger.warning("Failed to edit message: %s", e)
        return False
    except Exception as e:
        logger.error("Unexpected error editing message: %s", e)
        return False

async def safe_answer_callback(callback: CallbackQuery, text: str = "", show_alert: bool = False) -> bool:
    """Safely answer callback query."""
    try:
        await callback.answer(text, show_alert=show_alert)
        return True
    except Exception as e:
        logger.debug("Failed to answer callback: %s", e)
        return False