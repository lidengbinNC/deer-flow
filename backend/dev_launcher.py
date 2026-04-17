#!/usr/bin/env python
"""Unified local startup entrypoints for DeerFlow services.

Examples:
    uv run deerflow-dev langgraph
    uv run deerflow-dev gateway --reload
    uv run python dev_launcher.py langgraph --port 2024
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import os
import sys
from functools import wraps
from pathlib import Path


class DevLauncher:
    """Start common local development services with uv-friendly commands."""

    def __init__(self) -> None:
        self.backend_root = Path(__file__).resolve().parent
        self.harness_root = self.backend_root / "packages" / "harness"

    def run(self, argv: list[str] | None = None) -> int:
        parser = self._build_parser()
        args = parser.parse_args(argv)
        self._prepare_environment()
        self._patch_asyncio_run_for_debugger()
        return args.handler(args)

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="Start local DeerFlow development services.")
        subparsers = parser.add_subparsers(dest="service", required=True)

        langgraph_parser = subparsers.add_parser("langgraph", help="Start the LangGraph development server.")
        langgraph_parser.add_argument("--host", default="0.0.0.0", help="Bind host.")
        langgraph_parser.add_argument("--port", type=int, default=2024, help="Bind port.")
        langgraph_parser.add_argument(
            "--jobs",
            type=int,
            default=int(os.environ.get("LANGGRAPH_JOBS_PER_WORKER", "10")),
            help="Number of jobs per worker.",
        )
        langgraph_parser.add_argument(
            "--reload",
            action="store_true",
            help="Enable LangGraph auto-reload. Disabled by default for stable debugging.",
        )
        langgraph_parser.add_argument(
            "--allow-blocking",
            action="store_true",
            default=os.environ.get("LANGGRAPH_ALLOW_BLOCKING", "0") == "1",
            help="Pass --allow-blocking through to langgraph dev.",
        )
        langgraph_parser.set_defaults(handler=self._run_langgraph)

        gateway_parser = subparsers.add_parser("gateway", help="Start the FastAPI Gateway service.")
        gateway_parser.add_argument("--host", default="0.0.0.0", help="Bind host.")
        gateway_parser.add_argument("--port", type=int, default=8001, help="Bind port.")
        gateway_parser.add_argument(
            "--reload",
            action="store_true",
            help="Enable uvicorn auto-reload. Disabled by default for stable debugging.",
        )
        gateway_parser.set_defaults(handler=self._run_gateway)

        return parser

    def _prepare_environment(self) -> None:
        os.chdir(self.backend_root)

        required_paths = [str(self.backend_root), str(self.harness_root)]

        for path in reversed(required_paths):
            if path not in sys.path:
                sys.path.insert(0, path)

        python_path = os.environ.get("PYTHONPATH")
        entries = python_path.split(os.pathsep) if python_path else []
        normalized_entries = {entry for entry in entries if entry}

        for path in required_paths:
            if path not in normalized_entries:
                entries.insert(0, path)
                normalized_entries.add(path)

        os.environ["PYTHONPATH"] = os.pathsep.join(entries)

    @staticmethod
    def _patch_asyncio_run_for_debugger() -> None:
        """Make Python 3.12 uvicorn startup compatible with older PyCharm debuggers.

        PyCharm 2023.x patches ``asyncio.run`` during debug startup, but that patched
        function does not accept Python 3.12's ``loop_factory=`` keyword. Uvicorn 0.40+
        passes ``loop_factory``, which crashes only under the debugger.
        """
        parameters = inspect.signature(asyncio.run).parameters
        if "loop_factory" in parameters:
            return

        original_run = asyncio.run

        def compat_run(main, *, debug=None, loop_factory=None):  # type: ignore[override]
            if debug is not None:
                return original_run(main, debug=debug)
            return original_run(main)

        asyncio.run = compat_run

        # Uvicorn caches the helper at import time, so patch loaded modules too.
        for module_name, attr_name in (
            ("uvicorn.server", "asyncio_run"),
            ("uvicorn._compat", "asyncio_run"),
        ):
            module = sys.modules.get(module_name)
            if module is not None:
                setattr(module, attr_name, compat_run)

    def _run_langgraph(self, args: argparse.Namespace) -> int:
        cli_args = [
            "dev",
            "--no-browser",
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--n-jobs-per-worker",
            str(args.jobs),
        ]
        if not args.reload:
            cli_args.append("--no-reload")
        if args.allow_blocking:
            cli_args.append("--allow-blocking")
        return self._run_langgraph_cli(cli_args)

    def _run_gateway(self, args: argparse.Namespace) -> int:
        import uvicorn

        uvicorn.run(
            "app.gateway.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            reload_includes=["*.yaml", ".env"] if args.reload else None,
        )
        return 0

    @staticmethod
    def _run_langgraph_cli(argv: list[str]) -> int:
        DevLauncher._patch_dotenv_encoding_for_windows()
        try:
            import langgraph_cli.cli as langgraph_cli_module
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "LangGraph CLI module was not found in the active environment. "
                "Run `uv sync` or `uv sync --active` in `backend/` first."
            ) from exc

        try:
            langgraph_cli_module.cli.main(args=argv, prog_name="langgraph", standalone_mode=False)
        except SystemExit as exc:
            if exc.code is None:
                return 0
            if isinstance(exc.code, int):
                return exc.code
            return 1
        return 0

    @staticmethod
    def _patch_dotenv_encoding_for_windows() -> None:
        """Force UTF-8 dotenv decoding for Windows-local LangGraph startup."""
        if os.name != "nt":
            return

        try:
            import dotenv.main as dotenv_main
        except ModuleNotFoundError:
            return

        original_init = dotenv_main.DotEnv.__init__
        if getattr(original_init, "__deerflow_windows_utf8_patch__", False):
            return

        @wraps(original_init)
        def patched_init(
            self,
            dotenv_path,
            stream=None,
            verbose=False,
            encoding=None,
            interpolate=True,
            override=True,
        ):
            if encoding is None:
                encoding = "utf-8-sig"
            return original_init(
                self,
                dotenv_path=dotenv_path,
                stream=stream,
                verbose=verbose,
                encoding=encoding,
                interpolate=interpolate,
                override=override,
            )

        patched_init.__deerflow_windows_utf8_patch__ = True
        dotenv_main.DotEnv.__init__ = patched_init


def main() -> int:
    return DevLauncher().run()


if __name__ == "__main__":
    raise SystemExit(main())
