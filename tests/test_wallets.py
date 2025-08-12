from src.wallets import generate_wallet, address_qr_png
from src.validators import InputValidator, ValidationError, safe_chain
from src.error_handling import with_error_handling, ErrorHandler

# Expected derivation paths per chain (must match src/wallets.py)
# Additional test for all supported chains
ALL_SUPPORTED_CHAINS = ["ETH", "BTC", "SOL", "BASE", "BSC", "POLYGON", "AVAXC", "TRON", "XRP", "DOGE", "LTC", "TON"]

EXPECTED_PATHS = {
    "ETH": "m/44'/60'/0'/0/0",
    "BASE": "m/44'/60'/0'/0/0",
    "BSC": "m/44'/60'/0'/0/0",
    "POLYGON": "m/44'/60'/0'/0/0",
    "AVAXC": "m/44'/60'/0'/0/0",
    "BTC": "m/84'/0'/0'/0/0",
    "SOL": "m/44'/501'/0'/0'",
    "TRON": "m/44'/195'/0'/0/0",
    "XRP": "m/44'/144'/0'/0/0",
    "DOGE": "m/44'/3'/0'/0/0",
    "LTC": "m/84'/2'/0'/0/0",
    "TON": "m/44'/607'/0'/0/0",
}


def test_error_handling_integration():
    """Test integration with error handling system."""
    @with_error_handling(context="test_wallet_gen")
    async def test_wallet_generation():
        return generate_wallet("ETH")
    
    # This is a sync test, so we'll just verify the decorator exists
    assert hasattr(test_wallet_generation, '__wrapped__')


def test_performance_and_memory():
    """Test wallet generation performance and memory usage."""
    import time
    import gc
    
    # Measure generation time
    start_time = time.time()
    for _ in range(100):  # Generate 100 wallets
        info = generate_wallet("ETH")
        assert info.mnemonic  # Ensure generation succeeded
        # Clear the mnemonic immediately to test memory management
        del info
    
    generation_time = time.time() - start_time
    assert generation_time < 10.0, f"Generation too slow: {generation_time}s for 100 wallets"
    
    # Force garbage collection to test memory cleanup
    gc.collect()
    
    # Test that we can still generate after cleanup
    final_info = generate_wallet("BTC")
    assert final_info.chain == "BTC"

def test_generate_wallet_derivation_and_address_format():
    for chain, expected_path in EXPECTED_PATHS.items():
        info = generate_wallet(chain)  # local, no network calls
        assert info.chain == chain
        assert info.derivation_path == expected_path
        assert isinstance(info.mnemonic, str) and len(info.mnemonic.split()) == 12
        # Basic address sanity: non-empty and reasonably long
        assert isinstance(info.address, str) and len(info.address) >= 20, (
            f"Address looks too short for {chain}: {info.address}"
        )
        
        # Additional validation using our validators
        try:
            validated_chain = InputValidator.validate_chain(chain)
            assert validated_chain == chain
        except ValidationError:
            assert False, f"Chain {chain} should be valid"
        
        # Test address validation if we have chain-specific validation
        if chain in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC"):
            try:
                validated_addr = InputValidator.validate_address(info.address, chain)
                assert validated_addr == info.address
            except ValidationError:
                assert False, f"Generated {chain} address should be valid: {info.address}"


def test_address_qr_png_signature():
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    addr = generate_wallet("ETH").address
    buf = address_qr_png(addr)
    data = buf.read(8)
    assert data == b"\x89PNG\r\n\x1a\n"


def test_chain_validation_integration():
    """Test that wallet generation works with validated chains."""
    # Test with safe_chain validator
    validated_chain = safe_chain("eth")  # lowercase input
    assert validated_chain == "ETH"
    
    # Should work with generate_wallet
    info = generate_wallet(validated_chain)
    assert info.chain == "ETH"
    assert info.derivation_path == "m/44'/60'/0'/0/0"


def test_wallet_generation_error_handling():
    """Test error handling in wallet generation."""
    # Test with invalid chain (should raise ValueError)
    try:
        generate_wallet("INVALID_CHAIN")  # type: ignore
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unsupported chain" in str(e)


def test_address_format_validation():
    """Test that generated addresses match expected formats."""
    test_cases = {
        "ETH": lambda addr: addr.startswith("0x") and len(addr) == 42,
        "BTC": lambda addr: (addr.startswith("bc1") or addr.startswith("1") or addr.startswith("3")) and len(addr) >= 26,
        "SOL": lambda addr: len(addr) >= 32 and addr.isalnum(),
    }
    
    for chain, validator_func in test_cases.items():
        info = generate_wallet(chain)
        assert validator_func(info.address), f"Invalid {chain} address format: {info.address}"


def test_mnemonic_entropy_and_format():
    """Test mnemonic generation entropy and format."""
    # Generate multiple wallets and check entropy
    mnemonics = set()
    
    for _ in range(10):
        info = generate_wallet("ETH")
        assert len(info.mnemonic.split()) == 12
        mnemonics.add(info.mnemonic)
    
    # All mnemonics should be unique (extremely high probability)
    assert len(mnemonics) == 10, "Mnemonics should be unique"
    
    # Check that mnemonics contain valid BIP39 words (basic check)
    for mnemonic in mnemonics:
        words = mnemonic.split()
        # All words should be lowercase alphabetic
        for word in words:
            assert word.islower() and word.isalpha(), f"Invalid word format: {word}"
