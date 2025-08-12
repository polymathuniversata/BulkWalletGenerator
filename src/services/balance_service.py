"""
Balance checking service with performance optimizations and caching.
"""
import asyncio
import logging
from typing import List, Tuple, Dict, Optional
from decimal import Decimal, getcontext
import time
import json
from dataclasses import dataclass, asdict

import aiohttp

from ..config import get_rpc_config, get_balance_config

logger = logging.getLogger(__name__)
getcontext().prec = 80

@dataclass
class BalanceResult:
    """Balance check result."""
    address: str
    chain: str
    balance_raw: str
    balance_formatted: Decimal
    timestamp: int
    error: Optional[str] = None

class BalanceCache:
    """Simple in-memory cache for balance results."""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 minute default TTL
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Tuple[BalanceResult, int]] = {}
    
    def get(self, chain: str, address: str) -> Optional[BalanceResult]:
        """Get cached balance result."""
        key = f"{chain}:{address}"
        if key in self.cache:
            result, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                return result
            else:
                del self.cache[key]
        return None
    
    def set(self, result: BalanceResult) -> None:
        """Cache balance result."""
        key = f"{result.chain}:{result.address}"
        self.cache[key] = (result, int(time.time()))
    
    def clear_expired(self) -> int:
        """Remove expired cache entries."""
        now = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if now - timestamp >= self.ttl_seconds
        ]
        for key in expired_keys:
            del self.cache[key]
        return len(expired_keys)

class BalanceService:
    """High-performance balance checking service."""
    
    def __init__(self):
        self.rpc_config = get_rpc_config()
        self.balance_config = get_balance_config()
        self.cache = BalanceCache()
        self._stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0
        }
    
    async def get_evm_balances(self, chain: str, addresses: List[str]) -> List[Tuple[str, str, Decimal]]:
        """Get EVM balances with caching and batching."""
        if not addresses:
            return []
        
        # Check cache first
        cached_results = []
        uncached_addresses = []
        
        for address in addresses:
            cached = self.cache.get(chain, address)
            if cached and not cached.error:
                cached_results.append((address, cached.balance_raw, cached.balance_formatted))
                self._stats['cache_hits'] += 1
            else:
                uncached_addresses.append(address)
                self._stats['cache_misses'] += 1
        
        # Fetch uncached balances
        if uncached_addresses:
            try:
                fresh_results = await self._fetch_evm_balances_batch(chain, uncached_addresses)
                
                # Cache fresh results
                for addr, wei_hex, eth in fresh_results:
                    result = BalanceResult(
                        address=addr,
                        chain=chain,
                        balance_raw=wei_hex,
                        balance_formatted=eth,
                        timestamp=int(time.time())
                    )
                    self.cache.set(result)
                
                cached_results.extend(fresh_results)
                
            except Exception as e:
                logger.error(f"Failed to fetch {chain} balances: {e}")
                self._stats['errors'] += 1
                
                # Return cached results with empty results for failed addresses
                for address in uncached_addresses:
                    cached_results.append((address, "0x0", Decimal(0)))
        
        self._stats['total_requests'] += 1
        return cached_results
    
    async def _fetch_evm_balances_batch(self, chain: str, addresses: List[str]) -> List[Tuple[str, str, Decimal]]:
        """Fetch EVM balances using JSON-RPC batch requests."""
        rpc_url = self._get_evm_rpc_url(chain)
        if not rpc_url:
            raise RuntimeError(f"No RPC URL configured for {chain}")
        
        # Build batch request
        batch = []
        for i, addr in enumerate(addresses):
            batch.append({
                "jsonrpc": "2.0",
                "id": i,
                "method": "eth_getBalance",
                "params": [addr, "latest"],
            })
        
        # Execute batch request with timeout and retry
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Content-Type": "application/json"}
        ) as session:
            try:
                async with session.post(rpc_url, json=batch) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise RuntimeError(f"RPC error {response.status}: {text[:200]}")
                    
                    data = await response.json()
                    
            except asyncio.TimeoutError:
                raise RuntimeError("RPC request timeout")
            except aiohttp.ClientError as e:
                raise RuntimeError(f"RPC connection error: {e}")
        
        # Process batch response
        results = {item.get("id"): item for item in data if isinstance(item, dict)}
        out: List[Tuple[str, str, Decimal]] = []
        
        for i, addr in enumerate(addresses):
            item = results.get(i, {})
            result_hex = (item.get("result") or "0x0") if isinstance(item, dict) else "0x0"
            
            try:
                eth = self._wei_to_eth(result_hex)
            except Exception as e:
                logger.warning(f"Failed to parse balance for {addr}: {e}")
                eth = Decimal(0)
                result_hex = "0x0"
            
            out.append((addr, result_hex, eth))
        
        return out
    
    async def get_evm_balances_chunked(self, chain: str, addresses: List[str], chunk_size: int = 100) -> List[Tuple[str, str, Decimal]]:
        """Get EVM balances for large address lists using chunking."""
        if not addresses:
            return []
        
        results: List[Tuple[str, str, Decimal]] = []
        
        # Process in chunks to avoid RPC limits
        for i in range(0, len(addresses), chunk_size):
            chunk = addresses[i:i + chunk_size]
            try:
                chunk_results = await self.get_evm_balances(chain, chunk)
                results.extend(chunk_results)
                
                # Small delay between chunks to be respectful to RPC providers
                if i + chunk_size < len(addresses):
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Failed to process chunk {i//chunk_size + 1}: {e}")
                # Add zero balances for failed chunk
                for addr in chunk:
                    results.append((addr, "0x0", Decimal(0)))
        
        return results
    
    async def get_btc_balances(self, addresses: List[str]) -> List[Tuple[str, int, Decimal]]:
        """Get Bitcoin balances using Blockstream API."""
        if not self.balance_config.get('ENABLE_BTC_BAL'):
            raise RuntimeError("Bitcoin balance checking is disabled")
        
        api_base = self.balance_config.get('BTC_API_BASE', 'https://blockstream.info/api')
        results: List[Tuple[str, int, Decimal]] = []
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        ) as session:
            for address in addresses:
                # Check cache first
                cached = self.cache.get('BTC', address)
                if cached and not cached.error:
                    results.append((address, int(cached.balance_raw), cached.balance_formatted))
                    continue
                
                url = f"{api_base}/address/{address}"
                try:
                    async with session.get(url) as response:
                        if response.status != 200:
                            results.append((address, 0, Decimal(0)))
                            continue
                        
                        data = await response.json()
                        
                    chain_stats = data.get("chain_stats", {}) if isinstance(data, dict) else {}
                    funded = int(chain_stats.get("funded_txo_sum", 0))
                    spent = int(chain_stats.get("spent_txo_sum", 0))
                    sats = max(0, funded - spent)
                    btc = Decimal(sats) / Decimal(10**8)
                    
                    # Cache result
                    result = BalanceResult(
                        address=address,
                        chain='BTC',
                        balance_raw=str(sats),
                        balance_formatted=btc,
                        timestamp=int(time.time())
                    )
                    self.cache.set(result)
                    
                    results.append((address, sats, btc))
                    
                except Exception as e:
                    logger.warning(f"Failed to get BTC balance for {address}: {e}")
                    results.append((address, 0, Decimal(0)))
                
                # Rate limiting for external API
                await asyncio.sleep(0.2)
        
        return results
    
    async def get_sol_balances(self, addresses: List[str]) -> List[Tuple[str, int, Decimal]]:
        """Get Solana balances using JSON-RPC."""
        if not self.balance_config.get('ENABLE_SOL_BAL'):
            raise RuntimeError("Solana balance checking is disabled")
        
        rpc_url = self.balance_config.get('SOL_RPC_URL')
        if not rpc_url:
            raise RuntimeError("Missing SOL_RPC_URL")
        
        # Build batch request
        batch = []
        for i, address in enumerate(addresses):
            batch.append({
                "jsonrpc": "2.0",
                "id": i,
                "method": "getBalance",
                "params": [address],
            })
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            async with session.post(rpc_url, json=batch) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(f"SOL RPC error {response.status}: {text[:200]}")
                
                data = await response.json()
        
        results_map = {item.get("id"): item for item in data if isinstance(item, dict)}
        out: List[Tuple[str, int, Decimal]] = []
        
        for i, address in enumerate(addresses):
            lamports = 0
            item = results_map.get(i, {})
            if isinstance(item, dict):
                result = item.get("result") or {}
                if isinstance(result, dict):
                    lamports = int(result.get("value", 0))
            
            sol = Decimal(lamports) / Decimal(10**9)
            
            # Cache result
            balance_result = BalanceResult(
                address=address,
                chain='SOL',
                balance_raw=str(lamports),
                balance_formatted=sol,
                timestamp=int(time.time())
            )
            self.cache.set(balance_result)
            
            out.append((address, lamports, sol))
        
        return out
    
    def _get_evm_rpc_url(self, chain: str) -> Optional[str]:
        """Get RPC URL for EVM chain."""
        evm_rpc_mapping = {
            "ETH": "RPC_ETH",
            "BASE": "RPC_BASE", 
            "BSC": "RPC_BSC",
            "POLYGON": "RPC_POLYGON",
            "AVAXC": "RPC_AVAXC",
        }
        
        env_key = evm_rpc_mapping.get(chain)
        if not env_key:
            return None
        
        return self.rpc_config.get(env_key)
    
    def _wei_to_eth(self, wei_hex: str) -> Decimal:
        """Convert wei (hex) to ETH (decimal)."""
        try:
            wei_int = int(wei_hex, 16)
            return Decimal(wei_int) / Decimal(10**18)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert wei to eth: {wei_hex} - {e}")
            return Decimal(0)
    
    def get_service_stats(self) -> Dict:
        """Get service statistics."""
        cache_size = len(self.cache.cache)
        cache_hit_rate = (
            self._stats['cache_hits'] / (self._stats['cache_hits'] + self._stats['cache_misses'])
            if (self._stats['cache_hits'] + self._stats['cache_misses']) > 0 
            else 0
        )
        
        return {
            **self._stats,
            'cache_size': cache_size,
            'cache_hit_rate': f"{cache_hit_rate:.2%}"
        }
    
    def clear_cache(self) -> int:
        """Clear all cached balances."""
        count = len(self.cache.cache)
        self.cache.cache.clear()
        logger.info(f"Cleared {count} cached balance results")
        return count
    
    def cleanup_expired_cache(self) -> int:
        """Remove expired cache entries."""
        return self.cache.clear_expired()