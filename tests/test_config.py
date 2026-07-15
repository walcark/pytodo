import tomllib

from pytodo import config


def test_repo_config_toml_roundtrip(tmp_path):
    cfg = config.RepoConfig(
        categories=["work", "home"],
        urgency=config.Scale(
            ["now", "soon", "someday"], {"now": "bold red", "soon": "yellow"}
        ),
        horizon=config.Scale(["today", "week"]),
        sync_auto=False,
    )
    path = tmp_path / config.REPO_CONFIG_NAME
    path.write_text(cfg.to_toml(), encoding="utf-8")

    # readable as valid TOML
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["categories"]["values"] == ["work", "home"]
    assert data["urgency"]["colors"] == ["bold red", "yellow", ""]
    assert "colors" not in data["horizon"]  # no colors -> section omits the key
    assert data["sync"]["auto"] is False

    loaded = config.load_repo_config(tmp_path)
    assert loaded.categories == ["work", "home"]
    assert loaded.urgency.values == ["now", "soon", "someday"]
    assert loaded.urgency.style("now") == "bold red"
    assert loaded.horizon.values == ["today", "week"]
    assert loaded.sync_auto is False


def test_load_repo_config_defaults_when_missing(tmp_path):
    cfg = config.load_repo_config(tmp_path)
    assert cfg.categories == config.DEFAULT_CATEGORIES
    assert cfg.urgency.values == config.DEFAULT_URGENCY
    assert cfg.urgency.style("now") == "bold red"
    assert cfg.sync_auto is True


def test_local_config_read_write(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.read_data_dir() is None
    data_dir = tmp_path / "my-todo-data"
    written = config.write_data_dir(data_dir)
    assert written.exists()
    assert config.read_data_dir() == data_dir
