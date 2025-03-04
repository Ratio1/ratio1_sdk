"""


NOTE: if any of oracles return  data["result"]["oracle"]["manager"]["valid"] != True then
  - ommit that oracle from the list of oracles shown
  - display red warning containing the issue and the "certainty" 

>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 --rounds 8

Availability of node <0x693369781001bAC65F653856d0C00fA62129F407> from epoch 4 to epoch 6 on 8 rounds:
  Oracle #1:
    Address:   0xai_AleLPKqUHV-iPc-76-rUvDkRWW4dFMIGKW1xFVcy65nH
    ETH Addr:  0xE486F0d594e9F26931fC10c29E6409AEBb7b5144
    Alias:     nen-aid01
    Responses: 3
    Epochs:    [   4,    5,    6]
    Avails:    [   3,  254,  127]
    Cartainty: [0.99, 0.99, 0.99]
  Oracle #2:
    Address:   0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6
    ETH Addr:  0x129a21A78EBBA79aE78B8f11d5B57102950c1Fc0
    Alias:     nen-2
    Responses: 2
    Epochs:    [   4,    5,    6]
    Avails:    [   3,  254,  127]
    Cartainty: [0.99, 0.99, 0.99]
  Oracle #3: [RED due to not data["result"]["oracle"]["manager"]["valid"]]
    WARNING:   Oracle returned invalid data due to uncertainity
    Address:   0xai_A-Bn9grkqH1GUMTZUqHNzpX5DA6PqducH9_JKAlBx6YL
    ETH Addr:  0x93B04EF1152D81A0847C2272860a8a5C70280E14
    Alias:     nen-aid02
    Responses: 3
    Epochs:    [   4,    5,    6]
    Avails:    [   3,    0,  127]
    Cartainty: [0.99, 0.41, 0.99]


>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 --rounds 8

Availability of node <0x693369781001bAC65F653856d0C00fA62129F407> from epoch 4 to epoch 6 on 8 rounds:
  Oracle #1:
    Address:   0xai_AleLPKqUHV-iPc-76-rUvDkRWW4dFMIGKW1xFVcy65nH
    ETH Addr:  0xE486F0d594e9F26931fC10c29E6409AEBb7b5144
    Alias:     nen-aid01
    Responses: 3
    Avails:    [3, 254, 127]
  Oracle #2:
    Address:   0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6
    ETH Addr:  0x129a21A78EBBA79aE78B8f11d5B57102950c1Fc0
    Alias:     nen-2
    Responses: 3
    Avails:    [3, 254, 127]
  Oracle #3:
    Address:   0xai_A-Bn9grkqH1GUMTZUqHNzpX5DA6PqducH9_JKAlBx6YL
    ETH Addr:  0x93B04EF1152D81A0847C2272860a8a5C70280E14
    Alias:     nen-aid02
    Responses: 3
    Avails:    [3, 254, 127]



>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 --rounds 8
[if same oracle returns different avail dump the two confligting json with RED and stop command]    

>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 --full
[just dump json]


>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 
Availability of node <0x693369781001bAC65F653856d0C00fA62129F407> from epoch 4 to epoch 6:
Oracle address: 0xE486F0d594e9F26931fC10c29E6409AEBb7b5144
Oracle alias:   nen-aid01
Oracle report:
  - Epoch #4: 127 ( 50%)
  - Epoch #5: 254 (100%)
  - Epoch #6:   3 (  1%)
  
>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 # assuming current epoch is 10
Availability of node <0x693369781001bAC65F653856d0C00fA62129F407> from epoch 1 to epoch 9:
Oracle address: 0xE486F0d594e9F26931fC10c29E6409AEBb7b5144
Oracle alias:   nen-aid01
Oracle report:
  - Epoch #1: 127 ( 50%)
  - Epoch #2: 127 ( 50%)
  - Epoch #3: 127 ( 50%)
  - Epoch #4: 127 ( 50%)
  - Epoch #5: 254 (100%)
  - Epoch #6:   3 (  1%)
  - Epoch #7:  64 ( 25%)
  - Epoch #8:  33 ( 13%)
  - Epoch #9: 254 (100%)  
  
  
TODO: (future)
  - check ETH signature of the oracle data

"""

from ratio1.utils.config import log_with_color
from ratio1.utils.oracle_sync.oracle_tester import oracle_tester_init, handle_command_results


def get_availability(args):
  """
  This function is used to get the availability of the node.
  
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  
  node = args.node
  start = args.start or 1
  end = args.end
  full = args.json
  rounds = args.rounds or 1
  if str(rounds).isnumeric() and int(rounds) > 0:
    rounds = int(rounds)
  else:
    log_with_color("`rounds` must be a positive integer. Setting rounds to 1.", color='r')
    rounds = 1
  # endif rounds

  if isinstance(rounds, int) and rounds > 10:
    log_with_color("Rounds exceed the maximum limit of 10. Setting rounds to 10.", color='r')
    rounds = min(rounds, 10)

  if full:
    if rounds > 1:
      log_with_color("Cannot generate full JSON oracle network output in 'rounds' mode.", color='r')
      full = False
  # endif full

  tester = oracle_tester_init()
  
  if not tester.bc.is_valid_eth_address(node):
    node = tester.bc.node_address_to_eth_address(node)
  
  log_with_color("Checking {}availability of node <{}> from {} to {}.".format(
    "(DEBUG MODE) " if rounds > 1 else "", node, start,
    end if end else "last epoch"
    ), color='b'
  )
    
  
  res = tester.execute_command(
    node_eth_addr=node,
    start=start,
    end=end,
    rounds=rounds,
    debug=full
  )
  handle_command_results(res)
  return