from naeural_client.cli.nodes import get_nodes, get_supervisors
from naeural_client.utils.config import show_config, reset_config


# Define the available commands
CLI_COMMANDS = {
    "get": {
        "nodes": get_nodes,
        "supervisors": get_supervisors,
    },
    "config": {
        "show": show_config,
        "reset": reset_config,
    },
}