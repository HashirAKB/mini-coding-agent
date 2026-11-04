"""Command line entry point (filled in as milestones land)."""

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mini_agent")
    parser.parse_args(argv)
    return 0
