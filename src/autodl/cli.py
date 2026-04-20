"""Command-line entry point for AutoDL."""

import argparse
import importlib
import pkgutil
import sys
from collections.abc import Sequence
from typing import Protocol, cast

from autodl import commands


class CommandModule(Protocol):
    """Interface implemented by modules under ``autodl.commands``."""

    def get_help(self) -> str:
        """Return help text for the subcommand."""
        ...

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Register command-specific arguments on a parser."""
        ...

    def main(self, **kwargs: object) -> None:
        """Execute the subcommand."""
        ...


def main(argv: Sequence[str] | None = None) -> None:
    """Run the AutoDL command-line interface.

    Args:
        argv: Argument vector to parse. Defaults to ``sys.argv[1:]``.
    """
    parser = argparse.ArgumentParser(
        prog="autodl",
        description="AutoDL CLI",
    )
    subparsers = parser.add_subparsers(help="sub-command help", dest="command_name")
    modules_map: dict[str, CommandModule] = {}
    for command_name in (
        module.name
        for module in pkgutil.iter_modules(commands.__path__)
        if not module.name.startswith("_")
    ):
        module = cast(
            CommandModule, importlib.import_module(f"autodl.commands.{command_name}")
        )
        command_parser = subparsers.add_parser(
            command_name,
            help=module.get_help(),
        )
        module.add_arguments(command_parser)
        modules_map[command_name] = module
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    module = modules_map[options.command_name or "hunt"]
    del options.command_name
    module.main(**vars(options))
