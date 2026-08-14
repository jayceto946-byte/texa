#!/usr/bin/env python3
"""Legacy developer CLI. The supported product entry is Electron + FastAPI."""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Texa developer CLI (legacy)")
    parser.add_argument("mode", nargs="?", default="cli", choices=["cli"])
    parser.parse_args()
    from ui.cli import StudyCLI
    StudyCLI().run()


if __name__ == "__main__":
    main()
