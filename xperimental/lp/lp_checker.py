#!/usr/bin/env python3
from web3 import Web3

# Connect to Base mainnet RPC (chain ID 8453)
base_rpc = "https://base-mainnet.public.blastapi.io"
w3 = Web3(Web3.HTTPProvider(base_rpc))

# Uniswap V2 R1/USDC pair contract address
pair_address = Web3.to_checksum_address("0x0feC06fd2C2bd4066c7302c08950aBaA2E4AB1d3")

# Minimal ABI for Uniswap V2 pair (token0, token1, getReserves, totalSupply, balanceOf, and Transfer event)
pair_abi = [
    {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "getReserves", "outputs": [
        {"name": "reserve0", "type": "uint112"},
        {"name": "reserve1", "type": "uint112"},
        {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint"}], "type": "function"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "from", "type": "address"},
        {"indexed": True, "name": "to", "type": "address"},
        {"indexed": False, "name": "value", "type": "uint256"}],
     "name": "Transfer", "type": "event"}
]
pair_contract = w3.eth.contract(address=pair_address, abi=pair_abi)

# Fetch token addresses and pool data
token0 = pair_contract.functions.token0().call()       # Address of R1 or USDC
token1 = pair_contract.functions.token1().call()       # Address of the other token
reserve0, reserve1, _ = pair_contract.functions.getReserves().call()
total_supply = pair_contract.functions.totalSupply().call()

# Determine which reserve is R1 vs USDC by checking token symbols (optional)
erc20_abi = [{"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"}]
sym0 = w3.eth.contract(address=token0, abi=erc20_abi).functions.symbol().call().upper()
sym1 = w3.eth.contract(address=token1, abi=erc20_abi).functions.symbol().call().upper()
if sym0 == 'R1':
    r1_reserve, usdc_reserve = reserve0, reserve1
elif sym1 == 'R1':
    r1_reserve, usdc_reserve = reserve1, reserve0
else:
    # Fallback assumption if symbol check fails
    r1_reserve, usdc_reserve = reserve0, reserve1

# Prepare Transfer event signature hash for filtering logs
transfer_topic = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# Fetch all Transfer events from block 0 to latest for this pair contract
logs = w3.eth.get_logs({
    "fromBlock": 0,
    "toBlock": "latest",
    "address": pair_address,
    "topics": [transfer_topic]
})

# Collect all addresses that appear in Transfer logs
all_addresses = set()
for log in logs:
    # Topics[1] = from, Topics[2] = to (indexed fields)
    from_addr = "0x" + log['topics'][1].hex()[-40:]
    to_addr   = "0x" + log['topics'][2].hex()[-40:]
    # Convert to checksum addresses
    from_addr = Web3.to_checksum_address(from_addr)
    to_addr   = Web3.to_checksum_address(to_addr)
    # Add addresses if not zero address
    if from_addr != "0x0000000000000000000000000000000000000000":
        all_addresses.add(from_addr)
    if to_addr != "0x0000000000000000000000000000000000000000":
        all_addresses.add(to_addr)

# Filter for EOAs with positive LP balance
holders = {}
for addr in all_addresses:
    balance = pair_contract.functions.balanceOf(addr).call()
    if balance > 0:
        code = w3.eth.get_code(addr)
        # EOA check: get_code returns empty (0x) for EOAs:contentReference[oaicite:12]{index=12}
        if code == b'' or code == '0x' or code == b'0x' or code == b'0x0':
            holders[addr] = balance

# Compute and print each holder's share of R1 and USDC
for holder, bal in holders.items():
    share = bal / total_supply
    r1_amount = int(share * r1_reserve)
    usdc_amount = int(share * usdc_reserve)
    print(f"{holder}: R1={r1_amount}, USDC={usdc_amount}")
