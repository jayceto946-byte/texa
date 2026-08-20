#!/usr/bin/env python3
"""Developer launcher: legacy CLI and FastAPI web entry (Electron remains the product shell)."""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Texa developer CLI (legacy)")
    parser.add_argument("mode", nargs="?", default="cli", choices=["cli", "web"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.mode == "web":
        import uvicorn
        uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False)
        return
    from ui.cli import StudyCLI
    StudyCLI().run()


if __name__ == "__main__":
    main()
