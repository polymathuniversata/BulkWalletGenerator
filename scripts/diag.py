from src.wallets import generate_wallet

chains=["ETH","BTC","SOL","BASE","BSC","POLYGON","AVAXC","TRON","XRP","DOGE","LTC","TON"]
for c in chains:
    try:
        info=generate_wallet(c)
        print(c, info.derivation_path, len(info.mnemonic.split()), len(info.address))
    except Exception as e:
        print(c, 'ERROR', str(e))
