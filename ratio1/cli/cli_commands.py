"""
cli_commands.py
================

This module defines the command-line interface (CLI) commands 
for the Ratio1 SDK client. It provides a structured way to interact
with the SDK's functionalities through various commands and options
and it is used by cli.py

"""

from ratio1.cli.nodes import (
  get_nodes, get_supervisors, 
  restart_node, shutdown_node,
  get_apps
)
from ratio1.cli.oracles import get_availability
from ratio1.utils.config import (
  show_config, reset_config, show_address, get_set_network,
  get_networks, get_set_alias, get_eth_addr
)

# Define the available commands
CLI_COMMANDS = {
    "get": {
        "nodes": {
            "func": get_nodes,
            "description": "Get the list of nodes available in the network.",
            "params": {
                ### use "(flag)" at the end of the description to indicate a boolean flag
                ### otherwise it will be treated as a str parameter
                "--all": "Get all known nodes including those that have been gone missing (flag)",  # DONE
                "--online" : "Get only online nodes as seen by a active supervisor (flag)", # DONE
                "--peered": "Get only peered nodes - ie nodes that can be used by current client address (flag)",  # DONE
                "--supervisor" : "Use a specific supervisor node",
                "--eth" : "Use a specific node (flag)",
                "--wide" : "Display all available information (flag)",
            }
        },
        "supervisors": {
            "func": get_supervisors, # DONE
            "description": "Get the list of available supervisor oracles",
        },
        "eth" : {
            "func": get_eth_addr,
            "description": "Get the ETH address given a node address",
            "params": {
                "node": "The node address to get the ETH address for"
            }
        },
        "avail": {    
            "func": get_availability,
            "description": "Get the availability of a node via the oracle network.",
            "params": {
                ### use "(flag)" at the end of the description to indicate a boolean flag
                ### otherwise it will be treated as a str parameter
                "node": "The ETH address of the node to be checked via the oracle network.",
                "--start": "The start epoch number to check the availability from",
                "--end": "The end epoch number to check the availability to",
                "--json": "Enable full JSON oracle network output (flag)",
                "--rounds": "The number of rounds to check the availability for testing purposes (default=1)",
            }
        },
        "apps": {
            "func": get_apps,
            "description": "Get the apps running on a given node, if the client is allowed on that node.",
            "params": {
                "--node": "The ETH address or the specific address of the node to get the apps from",
                "--owner" : "Get the apps for a particular owner/initiator",
                "--full": "Include admin apps (flag)",
                "--json": "Output the entire JSON config of applications (flag)",
            }
        },
        "networks": {
            "func": get_networks, # DONE
            "description": "Show the network configuration",
        },
    },
    "config": {
        "show": {
            "func": show_config, # DONE
            "description": "Show the current configuration including the location",
        },
        "reset": {
            "func": reset_config, # DONE
            "description": "Reset the configuration to default",
            # "params": {
            #   ### use "(flag)" at the end of the description to indicate a boolean flag 
            #   ### otherwise it will be treated as a str parameter
            #   "--force": "Force reset (flag)",  # DONE
            # }
        },
        "addr": {
            "func": show_address, # DONE
            "description": "Show the current client address",
        },
        
        "network": {
            "func": get_set_network, # DONE
            "description": "Get/Set network",
            "params": {
                "--new": "The network to set either 'mainnet' or 'testnet' (same as --set)",
                "--set": "The network to set either 'mainnet' or 'testnet' (same as --new)",
            }
        },
        
        "alias" :{
            "func": get_set_alias, # DONE
            "description": "Show and sets the current client alias",
            "params": {
              "--set": "The alias to set for this SDK client",
            }
        }        
    },
    "restart": {
        "func": restart_node,
        "description": "Restart a node",
        "params": {
            "node": "The node to restart"
        }
    },
    "shutdown": {
        "func": shutdown_node,
        "description": "Shutdown a node",
        "params": {
            "node": "The node to shutdown"
        }
    }
}
