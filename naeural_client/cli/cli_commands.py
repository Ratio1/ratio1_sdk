from naeural_client.cli.nodes import (
  get_nodes, get_supervisors, 
  restart_node, shutdown_node
)
from naeural_client.utils.config import show_config, reset_config, show_address


# Define the available commands
CLI_COMMANDS = {
    "get": {
        "nodes": {
            "func": get_nodes,
            "params": {
              ### use "(flag)" at the end of the description to indicate a boolean flag 
              ### otherwise it will be treated as a str parameter
              "--all": "Get all known nodes including those that have been gone missing (flag)",  # DONE
              "--online" : "Get only online nodes as seen by a active supervisor (flag)", # DONE
              "--peered": "Get only peered nodes - ie nodes that can be used by current client address (flag)",  # DONE
              "--supervisor" : "Use a specific supervisor node"
            }
        },
        "supervisors": {
            "func": get_supervisors, # DONE
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
        },
        "addr": {
            "func": show_address, # DONE
            "description": "Show the current client address",
        }
    },
    "restart": {
        "func": restart_node, # TODO
        "params": {
            "node": "The node to restart"
        }
    },
    "shutdown": {
        "func": shutdown_node, # TODO
        "params": {
            "node": "The node to shutdown"
        }
    }
}
