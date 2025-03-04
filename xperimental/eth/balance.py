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
      
  
  l.P(f"Check #1 - default `{eng.evm_network}`", color='b')
  for address in addresses:
    eth_balance = eng.web3_get_balance_eth(address)    
    l.P(f"ETH Balance of {address} is {eth_balance:.4f} ETH")
    r1_balance = eng.web3_get_balance_r1(address)
    l.P(f"$R1 Balance of {address} is {r1_balance:.4f} R1")
    
  
  forced_network = "mainnet"
  l.P(f"Check #2 - forced `{forced_network}`", color='b')
  for address in addresses:
    eth_balance = eng.web3_get_balance_eth(address, network=forced_network)    
    l.P(f"ETH Balance of {address} is {eth_balance:.4f} ETH")
    r1_balance = eng.web3_get_balance_r1(address, network=forced_network)
    l.P(f"$R1 Balance of {address} is {r1_balance:.4f} R1")

  l.P(f"Check #3 - default `{eng.evm_network}`", color='b')
  for address in addresses:
    eth_balance = eng.web3_get_balance_eth(address)    
    l.P(f"ETH Balance of {address} is {eth_balance:.4f} ETH")
    r1_balance = eng.web3_get_balance_r1(address)
    l.P(f"$R1 Balance of {address} is {r1_balance:.4f} R1")

    
  eng.reset_network("mainnet")
  l.P(f"Check #4 - default `{eng.evm_network}`", color='b')
  for address in addresses:
    eth_balance = eng.web3_get_balance_eth(address)    
    l.P(f"ETH Balance of {address} is {eth_balance:.4f} ETH")
    r1_balance = eng.web3_get_balance_r1(address)
    l.P(f"$R1 Balance of {address} is {r1_balance:.4f} R1")
