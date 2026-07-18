"""Server configuration, read from the environment.

Everything the server needs to run is a plain value read from ``NEVERLAND_SERVER_*``
environment variables, optionally seeded from a ``KEY=VALUE`` config file (see
:meth:`ServerConfig.resolve`). Keeping config in the environment is what makes a
systemd unit and a container consume it identically, so one can replace the
other without touching the app.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from neverland.core.settings import read_data_dir

ENV_PREFIX = "NEVERLAND_SERVER_"
ENV_DATA_DIR = "NEVERLAND_SERVER_DATA_DIR"
ENV_HOST = "NEVERLAND_SERVER_HOST"
ENV_PORT = "NEVERLAND_SERVER_PORT"
ENV_TOKEN = "NEVERLAND_SERVER_TOKEN"
ENV_POLL_INTERVAL = "NEVERLAND_SERVER_POLL_INTERVAL"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_POLL_INTERVAL = 30.0

# Addresses that keep the server private to the machine (no token required).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class ConfigError(RuntimeError):
    """The server cannot start with the given environment."""


def default_config_path() -> Path:
    """Return the default config-file location (``$XDG_CONFIG_HOME/neverland``).

    The file is a ``KEY=VALUE`` env file, written by ``neverland-server setup`` and
    consumed both by ``neverland-server run`` and by the systemd unit's
    ``EnvironmentFile=`` directive, so a manual run and the service read the same
    settings.
    """
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "neverland" / "server.env"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a ``KEY=VALUE`` env file into a mapping.

    Blank lines and ``#`` comments are ignored. This is the systemd
    ``EnvironmentFile`` subset (no shell expansion, no quotes stripping), kept
    deliberately small so the same file is read identically here and by systemd.

    Parameters
    ----------
    path : pathlib.Path
        File to read.

    Returns
    -------
    dict of str to str
        The parsed key/value pairs.
    """
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if sep:
            values[key.strip()] = val.strip()
    return values


@dataclass
class ServerConfig:
    """Resolved server configuration.

    Attributes
    ----------
    data_dir : pathlib.Path
        Data repo the server reads and writes (a git working copy).
    host : str
        Bind address. Defaults to loopback; set it to the wireguard interface to
        expose the server only inside the tunnel, never ``0.0.0.0`` publicly.
    port : int
        Bind port.
    token : str or None
        Shared secret required on every API request. ``None`` leaves the server
        unauthenticated, which the CLI only allows on a loopback bind.
    poll_interval : float
        Seconds between background ``git pull`` cycles (0 disables the poller).
    """

    data_dir: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    token: str | None = None
    poll_interval: float = DEFAULT_POLL_INTERVAL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ServerConfig:
        """Build a config from ``NEVERLAND_SERVER_*`` variables.

        The data repo comes from ``NEVERLAND_SERVER_DATA_DIR`` or, failing that, the
        machine-local repo the CLI uses (:func:`neverland.core.settings.read_data_dir`).

        Raises
        ------
        ConfigError
            No data repo could be resolved, or a numeric value is malformed.
        """
        env = os.environ if environ is None else environ

        raw_dir = env.get(ENV_DATA_DIR)
        data_dir = Path(raw_dir).expanduser() if raw_dir else read_data_dir()
        if data_dir is None:
            raise ConfigError(
                f"No data repo: set {ENV_DATA_DIR} or run `todo init` first."
            )
        if not data_dir.exists():
            raise ConfigError(f"Data repo not found: {data_dir}")

        return cls(
            data_dir=data_dir,
            host=env.get(ENV_HOST, DEFAULT_HOST),
            port=_int(env, ENV_PORT, DEFAULT_PORT),
            token=env.get(ENV_TOKEN) or None,
            poll_interval=_float(env, ENV_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> ServerConfig:
        """Build a config from the config file overlaid with the environment.

        The config file (``config_path`` or :func:`default_config_path`) provides
        the base values; real ``NEVERLAND_SERVER_*`` environment variables override
        them, so a one-off ``NEVERLAND_SERVER_HOST=... neverland-server run`` still wins
        over the stored file.

        Raises
        ------
        ConfigError
            Same conditions as :meth:`from_env`.
        """
        path = config_path or default_config_path()
        base = load_env_file(path) if path.exists() else {}
        overrides = {k: v for k, v in os.environ.items() if k.startswith(ENV_PREFIX)}
        return cls.from_env({**base, **overrides})

    def is_loopback(self) -> bool:
        """Return whether the bind host keeps the server private to the machine."""
        return self.host in LOOPBACK_HOSTS


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    value = env.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {value!r}") from exc


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    value = env.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {value!r}") from exc
