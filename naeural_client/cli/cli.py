import argparse

from naeural_client.utils.config import maybe_init_config, log_with_color
from naeural_client.cli.cli_commands import CLI_COMMANDS

from naeural_client import version
import traceback


def create_global_parser():
  """
  Creates a global argument parser with shared options like verbosity.

  Returns
  -------
  argparse.ArgumentParser
      Global argument parser.
  """
  global_parser = argparse.ArgumentParser(add_help=False)  # Prevent duplicate help
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
  global_parser = create_global_parser()  # Add global parameters
  
  title = f"nepctl v{version} - CLI for Naeural Edge Protocol SDK package"
  parser = argparse.ArgumentParser(description=title, parents=[global_parser])
  subparsers = parser.add_subparsers(dest="command", help="Available commands")

  for command, subcommands in CLI_COMMANDS.items():
    command_parser = subparsers.add_parser(command, help=f"{command} commands")

    if isinstance(subcommands, dict) and "func" not in subcommands:
      # Nested subcommands
      command_subparsers = command_parser.add_subparsers(dest="subcommand")
      for subcommand, subcmd_info in subcommands.items():
        description = subcmd_info.get("description", f"{subcommand} command")
        subcommand_parser = command_subparsers.add_parser(
          subcommand, help=description
        )
        if isinstance(subcmd_info, dict) and "params" in subcmd_info:
          for param, description in subcmd_info["params"].items():
            if param.startswith("--"):
              if description.lower().endswith("(flag)"):
                subcommand_parser.add_argument(
                  param, action="store_true", help=description
                )
              else:
                subcommand_parser.add_argument(
                  param, help=description, type=str
                )
            else:
              subcommand_parser.add_argument(
                param, help=description
              )
            #end if
          #end for
        #end if
        subcommand_parser.set_defaults(func=subcmd_info["func"])
      #end for
      # Fallback help for `-h <subcommand>` like `nepctl -h config`
      command_parser.set_defaults(func=lambda args: command_parser.print_help())        
    else:
      # Single-level commands with parameters
      if "params" in subcommands:
        for param, description in subcommands["params"].items():
          if param.startswith("--"):
            command_parser.add_argument(
              param, action="store_true", help=description
            )
          else:
            command_parser.add_argument(
              param, help=description
            )
          #end if
      command_parser.set_defaults(func=subcommands["func"])

  return parser



def main():
  """
  Main entry point for the CLI.
  Ensures the configuration is initialized, builds the parser, 
  and executes the appropriate command function.
  """
  try:
    # Initialize configuration if necessary
    maybe_init_config()

    # Build the CLI parser
    parser = build_parser()
    args = parser.parse_args()

    # Check if a command function is provided
    if hasattr(args, "func"):
      args.func(args)  # Pass parsed arguments to the command function
    else:
      parser.print_help()

  except Exception as e:
    # Handle unexpected errors gracefully
    log_with_color(f"Error: {e}:\n{traceback.format_exc()}", color='r')


if __name__ == "__main__":
  main()
