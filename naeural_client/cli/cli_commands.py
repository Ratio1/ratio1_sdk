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
                "--all": "Get all known nodes", 
                "--online" : "Get only online nodes",
                # "--peered": "Get only peered nodes"
            }
        },
        "supervisors": {
            "func": get_supervisors,
        },
    },
    "config": {
        "show": {
            "func": show_config,
            "description": "Show the current configuration including the location",
        },
        "reset": {
            "func": reset_config,
            "description": "Reset the configuration to default",
        },
        "addr": {
            "func": show_address,
            "description": "Show the current client address",
        }
    },
    "restart": {
        "func": restart_node,
        "params": {
            "node": "The node to restart"
        }
    },
    "shutdown": {
        "func": shutdown_node,
        "params": {
            "node": "The node to shutdown"
        }
    }
}
