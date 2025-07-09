#!/usr/bin/env python3
"""Utility script for inspecting the R1/USDC liquidity pool on Base.

The script prints the current LP holders and the amount of R1 and USDC each
holder would receive if they removed their liquidity.  Additionally it computes
the "lower bound price" of the R1 token which is defined as the price implied by
the token balances inside the pair contract (reserves plus any unclaimed
trading fees).
"""

from web3 import Web3
from web3.exceptions import Web3RPCError
from typing import Iterable, Set
import logging
import math

# Connect to Base mainnet RPC (chain ID 8453)
base_rpc = "https://base-mainnet.public.blastapi.io"
w3 = Web3(Web3.HTTPProvider(base_rpc))

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)

# Uniswap V2 R1/USDC pair contract address
pair_address = Web3.to_checksum_address("0x0feC06fd2C2bd4066c7302c08950aBaA2E4AB1d3")

# Minimal ABI for Uniswap V2 pair (token0, token1, getReserves, totalSupply, balanceOf, and Transfer event)
pair_abi = [
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"},
        ],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint"}],
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]
pair_contract = w3.eth.contract(address=pair_address, abi=pair_abi)

erc20_abi = [
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]


def fetch_transfer_addresses(start_block: int, end_block: int, step: int = 10_000) -> Set[str]:
    """Return all addresses that ever transferred LP tokens."""

    transfer_topic = Web3.keccak(text="Transfer(address,address,uint256)").hex()
    addresses: Set[str] = set()
    for from_block in range(start_block, end_block + 1, step):
        to_block = min(from_block + step - 1, end_block)
        logger.debug("Fetching logs %s-%s", from_block, to_block)
        try:
            logs = w3.eth.get_logs(
                {
                    "fromBlock": from_block,
                    "toBlock": to_block,
                    "address": pair_address,
                    "topics": [transfer_topic],
                }
            )
        except Exception as exc:
            logger.warning("log request failed %s-%s: %s", from_block, to_block, exc)
            break
        for log in logs:
            from_addr = "0x" + log["topics"][1].hex()[-40:]
            to_addr = "0x" + log["topics"][2].hex()[-40:]
            if from_addr != "0x0000000000000000000000000000000000000000":
                addresses.add(Web3.to_checksum_address(from_addr))
            if to_addr != "0x0000000000000000000000000000000000000000":
                addresses.add(Web3.to_checksum_address(to_addr))
    return addresses


def compute_lower_bound_price(
    r1_balance: int, usdc_balance: int, r1_dec: int, usdc_dec: int
) -> float:
    """Return the minimal R1/USDC price implied by token balances."""

    r1_amt = r1_balance / (10**r1_dec)
    usdc_amt = usdc_balance / (10**usdc_dec)
    logger.debug("R1 balance=%s (%s decimals)", r1_amt, r1_dec)
    logger.debug("USDC balance=%s (%s decimals)", usdc_amt, usdc_dec)
    if r1_amt == 0:
        return 0.0
    return usdc_amt / r1_amt


def main() -> None:
    logger.info("Fetching pair metadata")
    latest_block = w3.eth.block_number

    token0 = pair_contract.functions.token0().call()
    token1 = pair_contract.functions.token1().call()
    reserve0, reserve1, _ = pair_contract.functions.getReserves().call()
    total_supply = pair_contract.functions.totalSupply().call()

    t0_contract = w3.eth.contract(address=token0, abi=erc20_abi)
    t1_contract = w3.eth.contract(address=token1, abi=erc20_abi)
    sym0 = t0_contract.functions.symbol().call().upper()
    sym1 = t1_contract.functions.symbol().call().upper()

    if sym0 == "R1":
        r1_reserve, usdc_reserve = reserve0, reserve1
        r1_contract, usdc_contract = t0_contract, t1_contract
    elif sym1 == "R1":
        r1_reserve, usdc_reserve = reserve1, reserve0
        r1_contract, usdc_contract = t1_contract, t0_contract
    else:
        r1_reserve, usdc_reserve = reserve0, reserve1
        r1_contract, usdc_contract = t0_contract, t1_contract
    logger.info("Reserves: R1=%s, USDC=%s", r1_reserve, usdc_reserve)

    r1_balance = r1_contract.functions.balanceOf(pair_address).call()
    usdc_balance = usdc_contract.functions.balanceOf(pair_address).call()

    lower_bound = compute_lower_bound_price(
        r1_balance,
        usdc_balance,
        r1_contract.functions.decimals().call(),
        usdc_contract.functions.decimals().call(),
    )
    logger.info("Lower bound price = %s", lower_bound)

    addresses = fetch_transfer_addresses(0, latest_block)
    logger.info("Found %d transfer addresses", len(addresses))
    holders = {}
    for addr in addresses:
        bal = pair_contract.functions.balanceOf(addr).call()
        if bal > 0 and w3.eth.get_code(addr) in (b"", b"0x", b"0x0", "0x"):
            holders[addr] = bal

    logger.info("EOA LP holders: %d", len(holders))
    for holder, bal in holders.items():
        share = bal / total_supply
        r1_amt = int(share * r1_reserve)
        usdc_amt = int(share * usdc_reserve)
        print(f"{holder}: R1={r1_amt}, USDC={usdc_amt}")

    logger.info("Lower bound price (R1/USDC) including fees: %s", lower_bound)
    print(f"Lower bound price (R1/USDC) including fees: {lower_bound}")


if __name__ == "__main__":
    main()
