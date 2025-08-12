"""
Tests for error handling utilities and decorators.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from aiogram.types import Message, CallbackQuery, User
from aiogram.exceptions import (
    TelegramNetworkError, 
    TelegramRetryAfter,
    TelegramBadRequest,
    TelegramForbiddenError
)

from src.error_handling import (
    with_error_handling,
    ErrorHandler,
    safe_async,
    safe_delete_message,
    safe_answer_callback,
    RateLimitHandler
)

class TestErrorHandler:
    """Test the ErrorHandler utility class."""
    
    def test_log_error_basic(self):
        """Test basic error logging functionality."""
        test_error = ValueError("Test error")
        
        with patch('src.error_handling.logger') as mock_logger:
            ErrorHandler.log_error(test_error, "test_context", 12345)
            mock_logger.error.assert_called_once()
            
        # Check error counting
        assert ErrorHandler.error_counts.get("ValueError", 0) > 0
    
    @pytest.mark.asyncio
    async def test_send_user_error_message(self):
        """Test sending error messages to users via Message."""
        # Mock message
        mock_message = AsyncMock(spec=Message)
        
        await ErrorHandler.send_user_error(mock_message, "Test error message")
        
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "Test error message" in call_args[0][0]
        assert "try again" in call_args[0][0].lower()
    
    @pytest.mark.asyncio
    async def test_send_user_error_callback(self):
        """Test sending error messages via CallbackQuery."""
        # Mock callback query
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.message = AsyncMock(spec=Message)
        
        await ErrorHandler.send_user_error(mock_callback, "Test error", show_retry=False)
        
        mock_callback.message.answer.assert_called_once()
        mock_callback.answer.assert_called_once()
        call_args = mock_callback.message.answer.call_args
        assert "Test error" in call_args[0][0]
        assert "try again" not in call_args[0][0].lower()  # show_retry=False
    
    def test_should_retry_logic(self):
        """Test retry logic for different error types."""
        # Network errors should retry
        assert ErrorHandler.should_retry(TelegramNetworkError("Network error"), 1, 3)
        assert ErrorHandler.should_retry(TelegramRetryAfter(10), 1, 3)
        
        # User errors should not retry
        assert not ErrorHandler.should_retry(TelegramBadRequest("Bad request"), 1, 3)
        assert not ErrorHandler.should_retry(TelegramForbiddenError("Forbidden"), 1, 3)
        
        # Max retries reached
        assert not ErrorHandler.should_retry(TelegramNetworkError("Network error"), 3, 3)


class TestErrorHandlingDecorator:
    """Test the error handling decorator."""
    
    @pytest.mark.asyncio
    async def test_successful_function(self):
        """Test decorator with successful function execution."""
        @with_error_handling(context="test_function")
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_telegram_network_error_retry(self):
        """Test retry behavior on network errors."""
        call_count = 0
        
        @with_error_handling(context="test_function", retry_count=3)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TelegramNetworkError("Network error")
            return "success"
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await test_func()
        
        assert result == "success"
        assert call_count == 3  # Failed twice, succeeded on third attempt
    
    @pytest.mark.asyncio
    async def test_bad_request_no_retry(self):
        """Test that bad requests don't trigger retries."""
        call_count = 0
        
        @with_error_handling(context="test_function")
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise TelegramBadRequest("Bad request")
        
        result = await test_func()
        
        assert result is None  # Should return None on unrecoverable error
        assert call_count == 1  # Should only be called once (no retries)
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test rate limit handling with proper backoff."""
        call_count = 0
        
        @with_error_handling(context="test_function")
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TelegramRetryAfter(1)  # 1 second backoff
            return "success"
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await test_func()
        
        assert result == "success"
        mock_sleep.assert_called_once_with(1)
    
    @pytest.mark.asyncio
    async def test_user_message_on_error(self):
        """Test that user messages are sent on errors."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        @with_error_handling(context="test_function", user_message="Custom error message")
        async def test_func(message):
            raise ValueError("Test error")
        
        with patch('src.error_handling.ErrorHandler.send_user_error', new_callable=AsyncMock) as mock_send_error:
            result = await test_func(mock_message)
        
        assert result is None
        mock_send_error.assert_called_once()
        args = mock_send_error.call_args[0]
        assert args[0] == mock_message
        assert "Custom error message" in args[1]
    
    @pytest.mark.asyncio
    async def test_forbidden_error_silent_fail(self):
        """Test that forbidden errors fail silently."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        @with_error_handling(context="test_function")
        async def test_func(message):
            raise TelegramForbiddenError("Bot blocked")
        
        with patch('src.error_handling.ErrorHandler.send_user_error', new_callable=AsyncMock) as mock_send_error:
            result = await test_func(mock_message)
        
        assert result is None
        # Should not send error message to blocked user
        mock_send_error.assert_not_called()


class TestSafeAsyncDecorator:
    """Test the safe async decorator."""
    
    @pytest.mark.asyncio
    async def test_safe_async_success(self):
        """Test safe async with successful function."""
        @safe_async
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_safe_async_error(self):
        """Test safe async with error (should return None)."""
        @safe_async
        async def test_func():
            raise ValueError("Test error")
        
        with patch('src.error_handling.logger') as mock_logger:
            result = await test_func()
        
        assert result is None
        mock_logger.error.assert_called_once()


class TestUtilityFunctions:
    """Test utility functions for safe operations."""
    
    @pytest.mark.asyncio
    async def test_safe_delete_message_success(self):
        """Test successful message deletion."""
        mock_message = AsyncMock(spec=Message)
        
        result = await safe_delete_message(mock_message)
        
        assert result is True
        mock_message.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_safe_delete_message_failure(self):
        """Test message deletion failure handling."""
        mock_message = AsyncMock(spec=Message)
        mock_message.delete.side_effect = TelegramBadRequest("Message not found")
        
        result = await safe_delete_message(mock_message)
        
        assert result is False
        mock_message.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_safe_delete_message_with_delay(self):
        """Test message deletion with delay."""
        mock_message = AsyncMock(spec=Message)
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await safe_delete_message(mock_message, delay=2.0)
        
        assert result is True
        mock_sleep.assert_called_once_with(2.0)
        mock_message.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_safe_answer_callback_success(self):
        """Test successful callback answering."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        
        result = await safe_answer_callback(mock_callback, "Success")
        
        assert result is True
        mock_callback.answer.assert_called_once_with("Success", show_alert=False)
    
    @pytest.mark.asyncio
    async def test_safe_answer_callback_failure(self):
        """Test callback answering failure handling."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.answer.side_effect = TelegramBadRequest("Callback expired")
        
        result = await safe_answer_callback(mock_callback, "Test")
        
        assert result is False
        mock_callback.answer.assert_called_once()


class TestRateLimitHandler:
    """Test the rate limit handler."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_handler_success(self):
        """Test successful function execution without rate limiting."""
        handler = RateLimitHandler()
        mock_message = AsyncMock(spec=Message)
        
        async def test_func():
            return "success"
        
        result = await handler.handle_rate_limit(test_func, mock_message)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_rate_limit_handler_retry(self):
        """Test rate limit handling with retry."""
        handler = RateLimitHandler(max_retries=2)
        mock_message = AsyncMock(spec=Message)
        
        call_count = 0
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TelegramRetryAfter(1)
            return "success"
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            with patch('src.error_handling.ErrorHandler.send_user_error', new_callable=AsyncMock):
                result = await handler.handle_rate_limit(test_func, mock_message)
        
        assert result == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_rate_limit_handler_max_retries(self):
        """Test rate limit handler with max retries exceeded."""
        handler = RateLimitHandler(max_retries=1)
        mock_message = AsyncMock(spec=Message)
        
        async def test_func():
            raise TelegramRetryAfter(1)
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            with patch('src.error_handling.ErrorHandler.send_user_error', new_callable=AsyncMock) as mock_send_error:
                result = await handler.handle_rate_limit(test_func, mock_message)
        
        assert result is None
        # Should send "overloaded" message
        mock_send_error.assert_called()
        args = mock_send_error.call_args[0]
        assert "overloaded" in args[1].lower()


class TestIntegrationScenarios:
    """Test realistic error scenarios."""
    
    @pytest.mark.asyncio
    async def test_network_error_recovery(self):
        """Test recovery from network errors."""
        attempts = 0
        
        @with_error_handling(context="network_test", retry_count=3)
        async def unstable_network_func():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TelegramNetworkError("Connection lost")
            return f"success_after_{attempts}_attempts"
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await unstable_network_func()
        
        assert result == "success_after_3_attempts"
    
    @pytest.mark.asyncio
    async def test_mixed_error_scenarios(self):
        """Test handling of different error types in sequence."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        # Simulate network error followed by success
        attempts = 0
        
        @with_error_handling(context="mixed_test")
        async def mixed_errors_func(message):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TelegramNetworkError("Network error")
            elif attempts == 2:
                return "success"
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await mixed_errors_func(mock_message)
        
        assert result == "success"
        assert attempts == 2


if __name__ == "__main__":
    pytest.main([__file__])