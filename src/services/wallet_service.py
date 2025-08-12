"""
Core wallet generation and management service.
"""
import time
import logging
from typing import Dict, Optional, Tuple
from decimal import Decimal

from ..wallets import generate_wallet, WalletInfo
from ..validators import safe_chain
from .balance_service import BalanceService

logger = logging.getLogger(__name__)

class SeedStore:
    """Secure temporary storage for seed phrases."""
    _data: Dict[int, Tuple[str, float]] = {}

    @classmethod
    def put(cls, user_id: int, mnemonic: str, ttl_seconds: int = 180) -> None:
        """Store seed with TTL."""
        cls._data[user_id] = (mnemonic, time.time() + ttl_seconds)

    @classmethod
    def take(cls, user_id: int) -> str | None:
        """Retrieve and remove seed (one-time use)."""
        rec = cls._data.pop(user_id, None)
        if not rec:
            return None
        mnemonic, expires = rec
        if time.time() > expires:
            return None
        return mnemonic

    @classmethod
    def cleanup_expired(cls) -> int:
        """Remove expired seeds and return count removed."""
        now = time.time()
        expired_users = [
            user_id for user_id, (_, expires) in cls._data.items() 
            if expires < now
        ]
        for user_id in expired_users:
            cls._data.pop(user_id, None)
        return len(expired_users)

class WalletService:
    """Core wallet generation and management service."""
    
    def __init__(self):
        self.balance_service = BalanceService()
        self._generation_stats = {
            'total_generated': 0,
            'by_chain': {},
            'by_user': {}
        }
    
    async def generate_wallet(self, chain: str, user_id: int) -> WalletInfo:
        """Generate a new wallet for the specified chain."""
        try:
            # Validate chain
            validated_chain = safe_chain(chain)
            
            # Generate wallet
            wallet_info = generate_wallet(validated_chain)
            
            # Update statistics
            self._update_generation_stats(validated_chain, user_id)
            
            logger.info(
                "Wallet generated successfully",
                extra={
                    'user_id': user_id,
                    'chain': validated_chain,
                    'address': wallet_info.address[:10] + "...",  # Partial address for logging
                }
            )
            
            return wallet_info
            
        except Exception as e:
            logger.error(
                "Wallet generation failed",
                extra={'user_id': user_id, 'chain': chain, 'error': str(e)}
            )
            raise
    
    def _update_generation_stats(self, chain: str, user_id: int) -> None:
        """Update internal generation statistics."""
        self._generation_stats['total_generated'] += 1
        self._generation_stats['by_chain'][chain] = self._generation_stats['by_chain'].get(chain, 0) + 1
        self._generation_stats['by_user'][user_id] = self._generation_stats['by_user'].get(user_id, 0) + 1
    
    def store_seed_temporarily(self, user_id: int, mnemonic: str, ttl_seconds: int = 180) -> None:
        """Store seed phrase temporarily for user retrieval."""
        SeedStore.put(user_id, mnemonic, ttl_seconds)
        logger.info(f"Seed stored temporarily for user {user_id} with {ttl_seconds}s TTL")
    
    def get_stored_seed(self, user_id: int) -> Optional[str]:
        """Retrieve stored seed (one-time use)."""
        seed = SeedStore.take(user_id)
        if seed:
            logger.info(f"Seed retrieved and consumed for user {user_id}")
        else:
            logger.info(f"No valid seed available for user {user_id}")
        return seed
    
    async def get_live_balance(self, chain: str, address: str) -> str:
        """Get live balance for display in wallet generation."""
        if chain not in ("ETH", "BASE", "BSC", "POLYGON", "AVAXC"):
            return ""
        
        try:
            balances = await self.balance_service.get_evm_balances(chain, [address])
            if balances and len(balances) > 0:
                _, _, eth = balances[0]
                return f"Balance: {eth} ETH-equivalent\\n"
        except Exception as e:
            logger.debug(f"Failed to get live balance for {chain} {address}: {e}")
        
        return ""
    
    async def bulk_generate(self, chain: str, count: int, user_id: int) -> list[WalletInfo]:
        """Generate multiple wallets efficiently."""
        wallets = []
        
        validated_chain = safe_chain(chain)
        
        logger.info(f"Starting bulk generation: {count} {validated_chain} wallets for user {user_id}")
        
        for i in range(count):
            try:
                wallet_info = await self.generate_wallet(validated_chain, user_id)
                wallets.append(wallet_info)
                
                # Periodic logging for large generations
                if count > 100 and (i + 1) % 100 == 0:
                    logger.info(f"Bulk generation progress: {i + 1}/{count}")
                    
            except Exception as e:
                logger.error(f"Failed to generate wallet {i + 1}/{count}: {e}")
                continue
        
        logger.info(f"Bulk generation completed: {len(wallets)}/{count} wallets generated")
        return wallets
    
    def get_generation_stats(self) -> dict:
        """Get wallet generation statistics."""
        return {
            **self._generation_stats,
            'active_seeds': len(SeedStore._data)
        }
    
    def cleanup_expired_seeds(self) -> int:
        """Clean up expired seeds and return count."""
        return SeedStore.cleanup_expired()
    
    async def validate_address_format(self, address: str, chain: str) -> bool:
        """Validate address format for the given chain."""
        try:
            from ..validators import InputValidator
            InputValidator.validate_address(address, chain)
            return True
        except Exception:
            return False
    
    def get_supported_chains(self) -> list[str]:
        """Get list of supported blockchain networks."""
        return ["ETH", "BTC", "SOL", "BASE", "BSC", "POLYGON", "AVAXC", "TRON", "XRP", "DOGE", "LTC", "TON"]
    
    def get_chain_info(self, chain: str) -> dict:
        """Get detailed information about a blockchain."""
        chain_info = {
            "ETH": {
                "name": "Ethereum",
                "description": "Smart contracts, DeFi, NFTs",
                "derivation_path": "m/44'/60'/0'/0/0",
                "address_format": "0x + 40 hex chars",
                "balance_supported": True
            },
            "BTC": {
                "name": "Bitcoin", 
                "description": "Digital gold, store of value",
                "derivation_path": "m/84'/0'/0'/0/0",
                "address_format": "bc1... (Bech32)",
                "balance_supported": True
            },
            "SOL": {
                "name": "Solana",
                "description": "Fast, low-cost transactions", 
                "derivation_path": "m/44'/501'/0'/0'",
                "address_format": "Base58 (32-44 chars)",
                "balance_supported": True
            },
            # Add more chain info as needed
        }
        
        return chain_info.get(chain, {
            "name": chain,
            "description": "Supported blockchain",
            "derivation_path": "Standard BIP44",
            "address_format": "Chain-specific",
            "balance_supported": False
        })