from naeural_client.cli.nodes import (
  get_nodes, get_supervisors, 
  restart_node, shutdown_node
)
from naeural_client.utils.config import show_config, reset_config


# Define the available commands
CLI_COMMANDS = {
    "get": {
        "nodes": {
            "func": get_nodes,
            "params": {
                "--all": "Get all nodes", 
                "--peered": "Get only peered nodes"
            }
        },
        "supervisors": {
            "func": get_supervisors,
        },
    },
    "config": {
        "show": {
            "func": show_config,
        },
        "reset": {
            "func": reset_config,
        },
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
