import os
from copy import deepcopy

from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



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
  
  l.P(f"ETH and $R1 transfer test on Ratio1:{eng.evm_network}")
  
  l.P("ETH Test")
  l.P(f"Src  {eng.eth_address} has {eng.web3_get_balance_eth():.4f} ETH")
  l.P(f"Dest {dest} has {eng.web3_get_balance_eth(dest):.4f} ETH")
  l.P(f"Sending 0.1 ETH to {dest}", color='b')
  tx_hash = eng.web3_send_eth(dest, 0.1, wait_for_tx=True, return_receipt=False)
  l.P(f"Executed tx: {tx_hash}", color='g')
  l.P(f"Src  {eng.eth_address} has {eng.web3_get_balance_eth():.4f} ETH")
  l.P(f"Dest {dest} has {eng.web3_get_balance_eth(dest):.4f} ETH")

  l.P("R1 Test")
  l.P(f"Src  {eng.eth_address} has {eng.web3_get_balance_r1():.4f} $R1")
  l.P(f"Dest {dest} has {eng.web3_get_balance_r1(dest):.4f} $R1")
  l.P(f"Sending 100 $R1 to {dest}", color='b')
  tx_hash = eng.web3_send_r1(dest, 100, wait_for_tx=True, return_receipt=False)
  l.P(f"Executed tx: {tx_hash}", color='g')
  l.P(f"Src  {eng.eth_address} has {eng.web3_get_balance_r1():.4f} $R1")
  l.P(f"Dest {dest} has {eng.web3_get_balance_r1(dest):.4f} $R1")
  