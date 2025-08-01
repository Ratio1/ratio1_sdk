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

  eng.reset_network("devnet")

  l.P(f"Allocate rewards across all escrows on Ratio1:{eng.evm_network}")
  
  l.P(f"Src  {eng.eth_address} has {eng.web3_get_balance_eth():.4f} ETH")
  tx_hash = eng.web3_allocate_rewards_across_all_escrows(wait_for_tx=True, return_receipt=True)
  l.P(f"Executed tx: {tx_hash}", color='g')