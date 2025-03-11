"""
cli.py
======

This script serves as the command-line interface (CLI) for the Ratio1 SDK.
It provides a user-friendly way to interact with the SDK's features and
functionalities through various commands and options.
"""

import signal
import sys
import argparse

from ratio1.utils.config import maybe_init_config, log_with_color
from ratio1.cli.cli_commands import CLI_COMMANDS
from ratio1 import version
import traceback

def handle_sigint(signum, frame):
  """Handler for the SIGINT signal (Ctrl-C)."""
  print("Interrupted. Exiting...")
  sys.exit(1)

def create_global_parser():
  """
  Creates a global argument parser with shared options like verbosity.

  Returns
  -------
  argparse.ArgumentParser
      Global argument parser.
  """
  global_parser = argparse.ArgumentParser(add_help=False)
  global_parser.add_argument(
    "-v", "--verbose", action="store_true", help="Enable verbose output"
  )
  return global_parser

def build_parser():
  """
  Dynamically builds the argument parser based on CLI_COMMANDS.

  Returns
  -------
  argparse.ArgumentParser
      Configured argument parser.
  """
  global_parser = create_global_parser()

  title = f"Ratio1 fleet control for SDK v{version} - CLI for ratio1 Edge Protocol SDK package"
  parser = argparse.ArgumentParser(description=title, parents=[global_parser])

  # Top-level subparsers (e.g. 'get', 'config', 'restart', 'shutdown')
  subparsers = parser.add_subparsers(dest="command", help="Available commands")
  subparsers.required = True  # Force user to pick a valid command

  for command, subcommands in CLI_COMMANDS.items():
    # Create a sub-parser for each top-level command
    cmd_help = subcommands.get("description") if "func" in subcommands else f"{command} commands"
    command_parser = subparsers.add_parser(command, help=cmd_help)

    # Check if this command has nested subcommands vs. a single-level function
    if isinstance(subcommands, dict) and "func" not in subcommands:
      # Nested subcommands (e.g. 'get nodes', 'get apps', etc.)
      command_subparsers = command_parser.add_subparsers(
        dest="subcommand",
        required=True,
        help=f"Subcommands under '{command}'"
      )

      for subcommand, subcmd_info in subcommands.items():
        description = subcmd_info.get("description", f"{subcommand} command")
        subcommand_parser = command_subparsers.add_parser(subcommand, help=description)

        # If we have parameters, add them
        if isinstance(subcmd_info, dict) and "params" in subcmd_info:
          for param, desc in subcmd_info["params"].items():
            if param.startswith("--"):
              if desc.lower().endswith("(flag)"):
                subcommand_parser.add_argument(param, action="store_true", help=desc)
              else:
                subcommand_parser.add_argument(param, type=str, help=desc)
            else:
              # Positional argument
              subcommand_parser.add_argument(param, help=desc)

        # Assign the function to call
        subcommand_parser.set_defaults(func=subcmd_info["func"])
    else:
      # Single-level command with optional parameters
      if "params" in subcommands:
        for param, desc in subcommands["params"].items():
          if param.startswith("--"):
            if desc.lower().endswith("(flag)"):
              command_parser.add_argument(param, action="store_true", help=desc)
            else:
              command_parser.add_argument(param, type=str, help=desc)
          else:
            command_parser.add_argument(param, help=desc)

      # Set the function to be called for this command
      command_parser.set_defaults(func=subcommands["func"])

  return parser

def main():
  """
  Main entry point for the CLI.
  Ensures the configuration is initialized, builds the parser,
  and executes the appropriate command function.
  """
  # Register SIGINT handler
  signal.signal(signal.SIGINT, handle_sigint)
  print("Processing...\r", end="", flush=True)

  try:
    initialized = maybe_init_config()

    if initialized:
      parser = build_parser()
      args = parser.parse_args()

      if hasattr(args, "func"):
        args.func(args)
      else:
        parser.print_help()

  except Exception as e:
    log_with_color(f"Error: {e}:\n{traceback.format_exc()}", color='r')

if __name__ == "__main__":
  main()
