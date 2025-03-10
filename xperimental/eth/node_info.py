import os
import json

from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  
  l = Logger("ENC")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    user_config=True,
    verbosity=2,
  )
  
  NODES = {
    "mainnet" : {
      "0x2539fDD57f93b267E58d5f2E6F77063C0230F6F4" : {
        "type" : "oracle",
      }, # oracle
      "0xdc4fDFd5B86aeA7BaB17d4742B7c39A2728Ff59B" : {
        "type" : "oracle",
      }, # oracle
      
      "0x63F01B4e15c68F9730Df94eBCc3975770c017059" : {
        "type" : "node",
      }, # node
      
      # fails:
      "0xa2Ee1AEC0A87BdfefcEa7E81Ed9d381430027E18" : {
        "type" : "fail",
      }, # fail - from testnet
    },
    "testnet" : {
      "0xE486F0d594e9F26931fC10c29E6409AEBb7b5144" : {
        "type" : "oracle",
      }, # oracle
      "0x93B04EF1152D81A0847C2272860a8a5C70280E14" : {
        "type" : "oracle",
      }, # oracle
      
      "0x76728138eDE2C3992f149f7fCe9550fa14b68335" : {
        "type" : "node",
      },# node
      
      # fails:
      "0x9A92a661bF2D844130Fed40dfae835448F09fDa3" : {
        "type" : "fail",
      }, # fail - from mainnet
    },
    "devnet" : {
      "0x49CD9D9528A4F6aEf94A0EB63E7745Eca4F9b57e" : {
        "type" : "oracle",
      }, # oracle
      "0x37379B80c7657620E5631832c4437B51D67A88cB" : {
        "type" : "oracle",
      }, # oracle
      
      "0xB8C3Ab8658680229aE7C7Eb25E63c49A9daa8DEc" : {
        "type" : "node",
      }, # node
      
      # fails:
      "0x129a21A78EBBA79aE78B8f11d5B57102950c1Fc0" : {
        "type" : "fail",
      }, # fail - from testnet
    },
  }
  
  
  for network, nodes in NODES.items():
    l.P(f"Resetting network {network}", color='y')
    eng.reset_network(network)        
    for node, pre_info in nodes.items():
      should_be_valid = pre_info['type'] != 'fail'
      node_info = eng.web3_get_node_info(node)
      is_valid = node_info['isValid']
      license_id = node_info['licenseId']      
      assign_time = node_info['assignTimestamp']
      str_assign_time = l.time_to_str(assign_time)
      owner = node_info['owner']
      owner_short = l.shorten_addr(owner)
      node_short = l.shorten_addr(node)
      check_status = is_valid != should_be_valid
      if check_status:      
        l.P(f"Node {node} check failed", color='r')
      else:
        if is_valid:
          l.P(f"Node {node_short} is valid, license {license_id} assigned at {str_assign_time} by owner {owner_short}", color='g')
        else:
          l.P(f"Node {node_short} is invalid as expected.", color='g')
  
  