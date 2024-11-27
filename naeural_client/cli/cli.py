import argparse

from naeural_client.utils.config import maybe_init_config, log_with_color
from naeural_client.cli.cli_commands import CLI_COMMANDS

from naeural_client import version

def build_parser():
  """
  Dynamically builds the argument parser based on CLI_COMMANDS.

  Returns
  -------
  argparse.ArgumentParser
      Configured argument parser.
  """
  descr = f"nepctl v{version} - CLI for Naeural Edge Protocol SDK package"
  parser = argparse.ArgumentParser(description=descr)
  subparsers = parser.add_subparsers(dest="command", help="Available commands")

  for command, subcommands in CLI_COMMANDS.items():
    command_parser = subparsers.add_parser(command, help=f"{command} commands")

    if isinstance(subcommands, dict) and "func" not in subcommands:
      # Nested subcommands
      command_subparsers = command_parser.add_subparsers(dest="subcommand")
      for subcommand, subcmd_info in subcommands.items():
        subcommand_parser = command_subparsers.add_parser(
          subcommand, help=f"{subcommand} command"
        )
        if isinstance(subcmd_info, dict) and "params" in subcmd_info:
          for param, description in subcmd_info["params"].items():
            if param.startswith("--"):
              subcommand_parser.add_argument(
                param, action="store_true", help=description
              )
            else:
              subcommand_parser.add_argument(
                param, help=description
              )
            #end if
          #end for
        #end if
        subcommand_parser.set_defaults(func=subcmd_info["func"])
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
    print(f"Error: {e}")


if __name__ == "__main__":
  main()
