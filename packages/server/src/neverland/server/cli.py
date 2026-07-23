"""The ``neverland-server`` command.

A small argparse CLI to manage the server process, separate from the ``todo``
command (which manages todos):

- ``run``: start the web server in the foreground (reads the config file + env).
- ``setup``: write the config file and generate an access token.
- ``install``: install a systemd *user* unit so the server survives logout/boot.
"""

from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
from pathlib import Path

from neverland.core.settings import read_data_dir

from . import deploy
from .config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ConfigError,
    ServerConfig,
    default_config_path,
)


def _run(args: argparse.Namespace) -> int:
    """Start the uvicorn server from the config file and environment."""
    import uvicorn

    from .app import create_app

    try:
        config = ServerConfig.resolve(_config_path(args))
    except ConfigError as exc:
        print(f"neverland-server: {exc}", file=sys.stderr)
        return 2

    # Flags win over both the config file and the environment: they are the
    # most explicit thing the user typed, and a one-off port is exactly what
    # you reach for when the stored one is already taken.
    if args.host is not None:
        config.host = args.host
    if args.port is not None:
        config.port = args.port

    if not config.is_loopback() and not config.token:
        print(
            f"neverland-server: refusing to bind {config.host} without a token "
            "(run `neverland-server setup` first, or bind 127.0.0.1).",
            file=sys.stderr,
        )
        return 2

    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)
    return 0


def _setup(args: argparse.Namespace) -> int:
    """Write the config file and generate an access token."""
    config_path = _config_path(args)
    if config_path.exists() and not args.force:
        print(
            f"neverland-server: config already exists: {config_path} "
            "(use --force to overwrite and rotate the token).",
            file=sys.stderr,
        )
        return 2

    data_dir = Path(args.data_dir).expanduser() if args.data_dir else read_data_dir()
    if data_dir is None:
        print(
            "neverland-server: no data repo: pass --data-dir or run `todo init` first.",
            file=sys.stderr,
        )
        return 2
    if not data_dir.exists():
        print(f"neverland-server: data repo not found: {data_dir}", file=sys.stderr)
        return 2

    token = secrets.token_urlsafe(32)
    deploy.write_env_file(
        config_path,
        {
            "NEVERLAND_SERVER_DATA_DIR": str(data_dir),
            "NEVERLAND_SERVER_HOST": args.host,
            "NEVERLAND_SERVER_PORT": str(args.port),
            "NEVERLAND_SERVER_TOKEN": token,
        },
    )

    print(f"Wrote {config_path} (mode 0600).")
    print(f"Data repo: {data_dir}")
    print(f"Bind: {args.host}:{args.port}")
    print(f"Access token: {token}")
    print(
        "\nNext: `neverland-server run` to start it, or `neverland-server install` "
        "for a systemd service."
    )
    return 0


def _install(args: argparse.Namespace) -> int:
    """Install (and, by default, start) the systemd user unit."""
    config_path = _config_path(args)
    if not config_path.exists():
        print(
            f"neverland-server: no config at {config_path}; "
            "run `neverland-server setup` first.",
            file=sys.stderr,
        )
        return 2

    unit_path = deploy.write_unit(config_path)
    print(f"Wrote {unit_path}.")

    if args.no_start:
        print("\nEnable it with:")
        print("  systemctl --user daemon-reload")
        print(f"  systemctl --user enable --now {deploy.UNIT_NAME}")
    elif not _start_service():
        return 1

    print(
        "\nTo keep it running after logout / across reboots:\n"
        "  loginctl enable-linger $USER"
    )
    return 0


def _start_service() -> bool:
    """Reload systemd and enable/start the unit; return whether it succeeded."""
    steps = (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", deploy.UNIT_NAME],
    )
    for cmd in steps:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"neverland-server: `{' '.join(cmd)}` failed:", file=sys.stderr)
            print(result.stderr.strip(), file=sys.stderr)
            print(
                "Run the systemctl commands manually (see `install --no-start`).",
                file=sys.stderr,
            )
            return False
    print(f"Started {deploy.UNIT_NAME}.")
    return True


def _config_path(args: argparse.Namespace) -> Path:
    """Resolve the config-file path from ``--config`` or the default."""
    override = getattr(args, "config", None)
    return Path(override).expanduser() if override else default_config_path()


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        metavar="PATH",
        help=f"Config file (default: {default_config_path()}).",
    )

    parser = argparse.ArgumentParser(prog="neverland-server", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser(
        "run", parents=[common], help="Run the web server (foreground)."
    )
    run.add_argument(
        "--host", help=f"Bind address, overriding the config (default: {DEFAULT_HOST})."
    )
    run.add_argument(
        "--port",
        type=int,
        help=f"Bind port, overriding the config (default: {DEFAULT_PORT}).",
    )
    run.set_defaults(func=_run)

    setup = sub.add_parser(
        "setup", parents=[common], help="Write the config file and a token."
    )
    setup.add_argument("--data-dir", help="Data repo (default: the CLI's repo).")
    setup.add_argument("--host", default=DEFAULT_HOST, help="Bind address.")
    setup.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port.")
    setup.add_argument(
        "--force", action="store_true", help="Overwrite and rotate the token."
    )
    setup.set_defaults(func=_setup)

    install = sub.add_parser(
        "install", parents=[common], help="Install the systemd user unit."
    )
    install.add_argument(
        "--no-start",
        action="store_true",
        help="Only write the unit; print the systemctl commands.",
    )
    install.set_defaults(func=_install)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``neverland-server`` console script."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
