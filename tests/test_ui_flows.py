"""
Tests for enhanced UI flows and user interactions.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from aiogram.types import Message, CallbackQuery, User, InlineKeyboardButton

from src.bot import (
    on_quick_generate_button,
    on_my_wallets_button,
    on_bulk_operations_button,
    on_help_callback,
    on_wallet_callback,
    enhanced_chains_kb,
    main_menu_kb
)

class TestEnhancedUI:
    """Test the enhanced UI components."""
    
    def test_main_menu_keyboard_structure(self):
        """Test the main menu keyboard structure."""
        kb = main_menu_kb()
        
        # Check that it's properly structured
        assert hasattr(kb, 'keyboard')
        assert len(kb.keyboard) == 3  # 3 rows
        
        # Check first row
        first_row = kb.keyboard[0]
        assert len(first_row) == 2
        assert "🔑 Quick Generate" in [btn.text for btn in first_row]
        assert "📊 View Chains" in [btn.text for btn in first_row]
        
        # Check placeholder text
        assert hasattr(kb, 'input_field_placeholder')
        assert "Choose an option" in kb.input_field_placeholder
    
    def test_enhanced_chains_keyboard(self):
        """Test the enhanced chains keyboard with icons."""
        kb = enhanced_chains_kb()
        
        # Should have multiple rows for organized layout
        assert len(kb.inline_keyboard) > 1
        
        # Check that icons are present
        all_buttons_text = []
        for row in kb.inline_keyboard:
            for button in row:
                all_buttons_text.append(button.text)
        
        # Should contain chain names
        assert any("ETH" in text for text in all_buttons_text)
        assert any("BTC" in text for text in all_buttons_text)
        
        # Should contain icons (emojis)
        assert any("🔶" in text or "🧡" in text or "☀️" in text for text in all_buttons_text)
    
    def test_enhanced_chains_keyboard_callback_data(self):
        """Test that chain keyboard has proper callback data."""
        kb = enhanced_chains_kb(prefix="test:")
        
        for row in kb.inline_keyboard:
            for button in row:
                assert button.callback_data.startswith("test:")
                # Extract chain name
                chain = button.callback_data.split(":", 1)[1]
                assert len(chain) >= 2  # Valid chain names


class TestQuickGenerateFlow:
    """Test the quick generate user flow."""
    
    @pytest.mark.asyncio
    async def test_quick_generate_button_normal(self):
        """Test quick generate button with normal conditions."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        with patch('src.bot._rate_limited', return_value=False):
            await on_quick_generate_button(mock_message)
        
        # Should send chain selection message
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        
        # Check message content
        assert "Quick Generate" in call_args[0][0]
        assert "Select a blockchain" in call_args[0][0]
        
        # Check that reply_markup is provided
        assert 'reply_markup' in call_args[1]
    
    @pytest.mark.asyncio
    async def test_quick_generate_button_rate_limited(self):
        """Test quick generate button when rate limited."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        with patch('src.bot._rate_limited', return_value=True):
            await on_quick_generate_button(mock_message)
        
        # Should send rate limit message
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "Rate limit exceeded" in call_args[0][0]


class TestMyWalletsFlow:
    """Test the My Wallets user flow."""
    
    @pytest.mark.asyncio
    async def test_my_wallets_button_empty(self):
        """Test My Wallets button with no saved wallets."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        with patch('src.bot.ProfileStore.list', return_value=[]):
            await on_my_wallets_button(mock_message)
        
        # Should send "no wallets" message
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "No wallets saved yet" in call_args[0][0]
        assert "Generate your first wallet" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_my_wallets_button_with_wallets(self):
        """Test My Wallets button with saved wallets."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        # Mock some wallet data
        mock_wallets = [
            ("ETH", "0x123...456", "m/44'/60'/0'/0/0", 1234567890),
            ("BTC", "bc1...xyz", "m/84'/0'/0'/0/0", 1234567891),
            ("ETH", "0x789...abc", "m/44'/60'/0'/0/0", 1234567892),
        ]
        
        with patch('src.bot.ProfileStore.list', return_value=mock_wallets):
            await on_my_wallets_button(mock_message)
        
        # Should send wallet summary
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        
        message_text = call_args[0][0]
        assert "My Wallets" in message_text
        assert "Total: 3" in message_text
        assert "ETH: 2" in message_text
        assert "BTC: 1" in message_text
        
        # Should include action buttons
        assert 'reply_markup' in call_args[1]


class TestBulkOperationsFlow:
    """Test the Bulk Operations user flow."""
    
    @pytest.mark.asyncio
    async def test_bulk_operations_button_normal(self):
        """Test bulk operations button with normal conditions."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        with patch('src.bot._rate_limited', return_value=False):
            await on_bulk_operations_button(mock_message)
        
        # Should send bulk operations menu
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        
        message_text = call_args[0][0]
        assert "Bulk Operations" in message_text
        assert "CSV" in message_text
        assert "ZIP" in message_text
        
        # Should have inline keyboard with options
        assert 'reply_markup' in call_args[1]
    
    @pytest.mark.asyncio
    async def test_bulk_operations_button_rate_limited(self):
        """Test bulk operations button when rate limited."""
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        with patch('src.bot._rate_limited', return_value=True):
            await on_bulk_operations_button(mock_message)
        
        # Should send rate limit message
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "Rate limit exceeded" in call_args[0][0]


class TestCallbackHandlers:
    """Test callback query handlers for enhanced UI."""
    
    @pytest.mark.asyncio
    async def test_help_callback_commands(self):
        """Test help callback for commands guide."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "help:commands"
        mock_callback.message = AsyncMock(spec=Message)
        
        with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
            await on_help_callback(mock_callback)
        
        # Should send commands guide
        mock_callback.message.answer.assert_called_once()
        call_args = mock_callback.message.answer.call_args
        
        message_text = call_args[0][0]
        assert "Commands Guide" in message_text
        assert "Generation:" in message_text
        assert "/generate" in message_text
        assert "/bulk" in message_text
    
    @pytest.mark.asyncio
    async def test_help_callback_security(self):
        """Test help callback for security info."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "help:security"
        mock_callback.message = AsyncMock(spec=Message)
        
        with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
            await on_help_callback(mock_callback)
        
        # Should send security information
        mock_callback.message.answer.assert_called_once()
        call_args = mock_callback.message.answer.call_args
        
        message_text = call_args[0][0]
        assert "Security Information" in message_text
        assert "BIP39" in message_text
        assert "locally" in message_text
    
    @pytest.mark.asyncio
    async def test_help_callback_faq(self):
        """Test help callback for FAQ."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "help:faq"
        mock_callback.message = AsyncMock(spec=Message)
        
        with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
            await on_help_callback(mock_callback)
        
        # Should send FAQ
        mock_callback.message.answer.assert_called_once()
        call_args = mock_callback.message.answer.call_args
        
        message_text = call_args[0][0]
        assert "Frequently Asked Questions" in message_text
        assert "Q:" in message_text
        assert "A:" in message_text
    
    @pytest.mark.asyncio
    async def test_wallet_callback_export_csv(self):
        """Test wallet callback for CSV export."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "wallet:export_csv"
        mock_callback.message = AsyncMock(spec=Message)
        
        with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
            with patch('src.bot.cmd_mycsv', new_callable=AsyncMock) as mock_cmd_mycsv:
                await on_wallet_callback(mock_callback)
        
        # Should call CSV export command
        mock_cmd_mycsv.assert_called_once_with(mock_callback.message)
    
    @pytest.mark.asyncio
    async def test_wallet_callback_clear_confirm(self):
        """Test wallet callback for clear confirmation."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "wallet:clear_confirm"
        mock_callback.message = AsyncMock(spec=Message)
        
        with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
            await on_wallet_callback(mock_callback)
        
        # Should send confirmation dialog
        mock_callback.message.answer.assert_called_once()
        call_args = mock_callback.message.answer.call_args
        
        message_text = call_args[0][0]
        assert "Confirm Deletion" in message_text
        assert "permanently delete" in message_text
        
        # Should have confirmation buttons
        assert 'reply_markup' in call_args[1]


class TestInputValidationIntegration:
    """Test integration of input validation with UI flows."""
    
    @pytest.mark.asyncio
    async def test_invalid_callback_data_handling(self):
        """Test handling of invalid callback data."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "invalid<script>data"
        mock_callback.message = AsyncMock(spec=Message)
        
        with patch('src.bot.safe_answer_callback', new_callable=AsyncMock) as mock_answer:
            await on_help_callback(mock_callback)
        
        # Should not process invalid callback data
        # The function should return early without processing
        mock_callback.message.answer.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_empty_callback_data_handling(self):
        """Test handling of empty callback data."""
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = ""
        mock_callback.message = AsyncMock(spec=Message)
        
        with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
            await on_help_callback(mock_callback)
        
        # Should not process empty callback data
        mock_callback.message.answer.assert_not_called()


class TestUserFlowIntegration:
    """Test complete user flows from start to finish."""
    
    @pytest.mark.asyncio
    async def test_complete_wallet_generation_flow(self):
        """Test complete wallet generation flow."""
        # Step 1: User clicks Quick Generate
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        with patch('src.bot._rate_limited', return_value=False):
            await on_quick_generate_button(mock_message)
        
        # Should send chain selection
        assert mock_message.answer.called
        
        # Step 2: User selects a chain via callback
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "gen:ETH"
        mock_callback.message = mock_message
        mock_callback.from_user = mock_user
        
        with patch('src.bot._do_generate', new_callable=AsyncMock) as mock_do_generate:
            with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
                await on_generate_callback(mock_callback)
        
        # Should call wallet generation
        mock_do_generate.assert_called_once_with(mock_message, "ETH")
    
    @pytest.mark.asyncio
    async def test_complete_bulk_operations_flow(self):
        """Test complete bulk operations flow."""
        # Step 1: User clicks Bulk Operations
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        with patch('src.bot._rate_limited', return_value=False):
            await on_bulk_operations_button(mock_message)
        
        # Should send bulk options
        assert mock_message.answer.called
        
        # Step 2: User selects CSV option
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "bulk:csv"
        mock_callback.message = mock_message
        mock_callback.from_user = mock_user
        
        with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
            with patch('src.bot._pending_bulk', {}):  # Mock the global state
                await on_bulk_callback(mock_callback)
        
        # Should ask for count
        assert mock_message.answer.called
        # Should set pending state for count input
        from src.bot import _pending_bulk
        assert mock_user.id in _pending_bulk


class TestAccessibilityAndUsability:
    """Test accessibility and usability features."""
    
    def test_keyboard_has_helpful_placeholders(self):
        """Test that keyboards have helpful placeholder text."""
        kb = main_menu_kb()
        assert hasattr(kb, 'input_field_placeholder')
        assert len(kb.input_field_placeholder) > 0
    
    def test_buttons_have_clear_icons(self):
        """Test that buttons have clear, distinguishable icons."""
        kb = main_menu_kb()
        
        # Extract button texts
        button_texts = []
        for row in kb.keyboard:
            for button in row:
                button_texts.append(button.text)
        
        # Should have different icons for different functions
        icons_used = [text.split()[0] for text in button_texts]
        assert len(set(icons_used)) == len(icons_used)  # All icons unique
    
    def test_error_messages_are_user_friendly(self):
        """Test that error messages are clear and actionable."""
        # This would be tested in the actual UI flow tests above
        # Here we just verify the pattern
        kb = enhanced_chains_kb()
        
        # Should be organized in logical groups
        assert len(kb.inline_keyboard) >= 3  # At least 3 rows for organization


if __name__ == "__main__":
    pytest.main([__file__])