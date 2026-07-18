# neverland-server

[![PyPI](https://img.shields.io/pypi/v/neverland-server)](https://pypi.org/project/neverland-server/)
![Python](https://img.shields.io/pypi/pyversions/neverland-server)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB)

A self-hosted FastAPI server and React web UI for
[neverland](https://github.com/walcark/neverland), built on the shared core. It
serves a read-only viewer plus quick capture, behind a mandatory bearer token.

> *Growing up means remembering deadlines. Neverland remembers them for you.*

## Install

```sh
pipx install neverland-server
```

## Quick start

```sh
neverland-server setup       # generate a token and a config file (0600)
neverland-server run         # start the server in the foreground
```

The web UI prompts for the token on first load and stores it in the browser's
`localStorage`. The server refuses a non-loopback bind unless a token is set.

## Deploy

```sh
neverland-server install     # write and start a systemd user unit
loginctl enable-linger $USER # keep it running across reboots
```

Bind it to a private interface (e.g. wireguard), never a public `0.0.0.0`.
Configuration is read from `~/.config/neverland/server.env` and overridable via
`NEVERLAND_SERVER_*` environment variables. See the
[main README](https://github.com/walcark/neverland#web-server) for the full
server guide.
