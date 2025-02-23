import os
from copy import deepcopy

from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    verbosity=2,
  )
  with open("xperimental/eth/addrs.txt", "rt") as fd:
    lines = fd.readlines()
    addresses = [line.strip() for line in lines]
    
  dest = addresses[0]
  
  l.P(f"Src  {eng.eth_address} has {eng.web3_get_balance():.4f} ETH")
  l.P(f"Dest {dest} has {eng.web3_get_balance(dest):.4f} ETH")
  l.P(f"Sending 0.1 ETH to {dest}", color='b')
  tx_receipt = eng.wallet_send_eth(dest, 0.1, wait_for_tx=True)
  l.P(f"Executed tx: {tx_receipt.transactionHash}", color='g')
  l.P(f"Src  {eng.eth_address} has {eng.web3_get_balance():.4f} ETH")
  l.P(f"Dest {dest} has {eng.web3_get_balance(dest):.4f} ETH")
  