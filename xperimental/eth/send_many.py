import os
import time
from copy import deepcopy
import numpy as np

from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    verbosity=2,
  )
  with open("xperimental/eth/mynodes.txt", "rt") as fd:
    lines = fd.readlines()
    addresses = [line.strip() for line in lines]
  
  assert eng.evm_network in ['testnet', 'devnet']
  client_eth = eng.web3_get_balance_eth()
  client_r1 = eng.web3_get_balance_r1()
  n_peers = len(addresses)
  amount_eth = (client_eth / 2) / n_peers
  amount_r1 = (client_r1 / 2) / n_peers
  l.P(
    f"Client {eng.eth_address}:\n  {client_eth:>10.4f} ETH\n  {client_r1:>10.4f} $R1\n  Will distribute (max) {amount_eth:.4f} ETH\n  Will distribute (MAX) {amount_r1:.4f} $R1 \n  to each of {n_peers} peers",
    color='g'
  )

  for address in addresses:
    random_amount_eth = np.random.uniform(0.7, 0.99) * amount_eth
    random_amount_r1 = np.random.uniform(0.7, 1.1) * amount_r1
    l.P(f"  Sending {random_amount_eth:.4f} ETH to {address}", color='b')
    tx_hash = eng.web3_send_eth(address, random_amount_eth, wait_for_tx=True, return_receipt=False)
    time.sleep(2) # bit of extra sleep time
    l.P(f"  Executed tx: {tx_hash}", color='g')

    l.P(f"  Sending {random_amount_r1:.4f} $R1 to {address}", color='b')
    tx_hash = eng.web3_send_r1(address, random_amount_r1, wait_for_tx=True, return_receipt=False)
    time.sleep(2) # bit of extra sleep time
    l.P(f"  Executed tx: {tx_hash}", color='g')
    eth_balance = eng.web3_get_balance_eth(address)
    r1_balance = eng.web3_get_balance_r1(address)
    l.P(f"  ETH Balance of {address} is {eth_balance:.4f} ETH")
    l.P(f"  R1 Balance of {address} is {r1_balance:.4f} R1")
  
  time.sleep(5)
  client_eth = eng.web3_get_balance_eth()
  client_r1 = eng.web3_get_balance_r1()
  l.P(f"Client has {client_eth:.4f} ETH and {client_r1:.4f} $R1")  