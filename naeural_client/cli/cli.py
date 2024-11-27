import argparse

from naeural_client.utils.config import maybe_init_config
from naeural_client.cli.cli_commands import CLI_COMMANDS

def build_parser():
  """
  Dynamically builds the argument parser based on CLI_COMMANDS.

  Returns
  -------
  argparse.ArgumentParser
      Configured argument parser.
  """
  parser = argparse.ArgumentParser(description="nepctl  - CLI for Naeural Edge Protocol SDK package")
  subparsers = parser.add_subparsers(dest="command", help="Available commands")

  # Iterate over top-level commands
  for command, subcommands in CLI_COMMANDS.items():
    command_parser = subparsers.add_parser(command, help=f"{command} commands")
    if isinstance(subcommands, dict):  # Nested subcommands
      command_subparsers = command_parser.add_subparsers(dest="subcommand")
      for subcommand, func in subcommands.items():
        subcommand_parser = command_subparsers.add_parser(
            subcommand, help=f"{subcommand} command"
        )
        subcommand_parser.set_defaults(func=func)
    else:
      command_parser.set_defaults(func=subcommands)

  return parser

def main():
  maybe_init_config()
  parser = build_parser()
  args = parser.parse_args()
  if hasattr(args, "func"):
    args.func()  # Call the dynamically loaded function
  else:
    parser.print_help()

if __name__ == "__main__":
  main()
