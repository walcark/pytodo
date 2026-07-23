import stat

import pytest

from neverland.server import cli, deploy
from neverland.server.config import (
    ServerConfig,
    default_config_path,
    load_env_file,
)


def test_default_config_path_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "neverland" / "server.env"


def test_load_env_file_skips_blanks_and_comments(tmp_path):
    path = tmp_path / "server.env"
    path.write_text(
        "# comment\n\nNEVERLAND_SERVER_PORT=9000\nNEVERLAND_SERVER_HOST=0.0.0.0\n"
    )
    assert load_env_file(path) == {
        "NEVERLAND_SERVER_PORT": "9000",
        "NEVERLAND_SERVER_HOST": "0.0.0.0",
    }


def test_resolve_merges_file_then_env(tmp_path, monkeypatch):
    path = tmp_path / "server.env"
    deploy.write_env_file(
        path,
        {
            "NEVERLAND_SERVER_DATA_DIR": str(tmp_path),
            "NEVERLAND_SERVER_PORT": "9000",
            "NEVERLAND_SERVER_TOKEN": "from-file",
        },
    )
    # Real environment overrides the file.
    monkeypatch.setenv("NEVERLAND_SERVER_PORT", "7000")
    monkeypatch.delenv("NEVERLAND_SERVER_TOKEN", raising=False)

    config = ServerConfig.resolve(path)
    assert config.port == 7000  # env wins
    assert config.token == "from-file"  # file fills the gap


def test_write_env_file_is_owner_only(tmp_path):
    path = tmp_path / "sub" / "server.env"
    deploy.write_env_file(path, {"NEVERLAND_SERVER_TOKEN": "abc"})
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    assert path.read_text() == "NEVERLAND_SERVER_TOKEN=abc\n"


def test_render_unit_has_environment_and_execstart(tmp_path):
    unit = deploy.render_unit(tmp_path / "server.env", "/usr/bin/neverland-server")
    assert f"EnvironmentFile={tmp_path / 'server.env'}" in unit
    assert "ExecStart=/usr/bin/neverland-server run" in unit
    assert "WantedBy=default.target" in unit


def test_is_loopback():
    assert ServerConfig(data_dir=".").is_loopback()  # default 127.0.0.1
    assert not ServerConfig(data_dir=".", host="0.0.0.0").is_loopback()


# --- CLI ---------------------------------------------------------------------


def test_setup_writes_config_with_token(tmp_path, capsys):
    config_path = tmp_path / "server.env"
    rc = cli.main(["setup", "--config", str(config_path), "--data-dir", str(tmp_path)])
    assert rc == 0
    values = load_env_file(config_path)
    assert values["NEVERLAND_SERVER_DATA_DIR"] == str(tmp_path)
    assert len(values["NEVERLAND_SERVER_TOKEN"]) >= 32
    assert values["NEVERLAND_SERVER_TOKEN"] in capsys.readouterr().out


def test_setup_refuses_to_overwrite(tmp_path):
    config_path = tmp_path / "server.env"
    args = ["setup", "--config", str(config_path), "--data-dir", str(tmp_path)]
    assert cli.main(args) == 0
    first = load_env_file(config_path)["NEVERLAND_SERVER_TOKEN"]

    assert cli.main(args) == 2  # exists, no --force
    assert load_env_file(config_path)["NEVERLAND_SERVER_TOKEN"] == first  # unchanged

    assert cli.main(args + ["--force"]) == 0  # --force rotates it
    assert load_env_file(config_path)["NEVERLAND_SERVER_TOKEN"] != first


def test_setup_missing_data_repo(tmp_path):
    rc = cli.main(
        ["setup", "--config", str(tmp_path / "server.env"), "--data-dir", "/no/such"]
    )
    assert rc == 2


def test_install_writes_unit(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_path = tmp_path / "server.env"
    deploy.write_env_file(config_path, {"NEVERLAND_SERVER_DATA_DIR": str(tmp_path)})

    rc = cli.main(["install", "--config", str(config_path), "--no-start"])
    assert rc == 0
    unit = (tmp_path / "systemd" / "user" / deploy.UNIT_NAME).read_text()
    assert f"EnvironmentFile={config_path}" in unit


def test_install_needs_config(tmp_path):
    rc = cli.main(["install", "--config", str(tmp_path / "absent.env"), "--no-start"])
    assert rc == 2


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_run_refuses_public_bind_without_token(tmp_path, monkeypatch, host, capsys):
    # A public bind with no token must be refused before uvicorn starts.
    config_path = tmp_path / "server.env"
    deploy.write_env_file(
        config_path,
        {"NEVERLAND_SERVER_DATA_DIR": str(tmp_path), "NEVERLAND_SERVER_HOST": host},
    )
    for var in ("NEVERLAND_SERVER_HOST", "NEVERLAND_SERVER_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    started = {}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: started.setdefault("ran", True))

    rc = cli.main(["run", "--config", str(config_path)])
    if host == "0.0.0.0":
        assert rc == 2
        assert "ran" not in started
        assert "without a token" in capsys.readouterr().err
    else:
        assert rc == 0
        assert started.get("ran")


def test_run_port_flag_overrides_config(tmp_path, monkeypatch):
    # The flag is the most explicit input: it must beat the stored config.
    config_path = tmp_path / "server.env"
    deploy.write_env_file(
        config_path,
        {"NEVERLAND_SERVER_DATA_DIR": str(tmp_path), "NEVERLAND_SERVER_PORT": "8000"},
    )
    for var in ("NEVERLAND_SERVER_HOST", "NEVERLAND_SERVER_PORT"):
        monkeypatch.delenv(var, raising=False)

    seen = {}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: seen.update(k))

    rc = cli.main(["run", "--config", str(config_path), "--port", "8123"])
    assert rc == 0
    assert seen["port"] == 8123


def test_run_host_flag_still_requires_a_token(tmp_path, monkeypatch, capsys):
    # Overriding the host must not slip past the public-bind guard.
    config_path = tmp_path / "server.env"
    deploy.write_env_file(config_path, {"NEVERLAND_SERVER_DATA_DIR": str(tmp_path)})
    for var in ("NEVERLAND_SERVER_HOST", "NEVERLAND_SERVER_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    started = {}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: started.setdefault("ran", True))

    rc = cli.main(["run", "--config", str(config_path), "--host", "0.0.0.0"])
    assert rc == 2
    assert "ran" not in started
    assert "without a token" in capsys.readouterr().err
