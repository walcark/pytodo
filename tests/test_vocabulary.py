from pytodo.vocabulary import (
    DEFAULT_AREAS,
    DEFAULT_CONTEXTS,
    RepoConfig,
    load_repo_config,
    save_repo_config,
)


def test_defaults_when_no_file(tmp_path):
    cfg = load_repo_config(tmp_path)
    assert cfg.areas == DEFAULT_AREAS
    assert cfg.contexts == DEFAULT_CONTEXTS
    assert cfg.sync_auto is True
    assert cfg.waiting_stale_days == 7


def test_roundtrip_through_toml(tmp_path):
    cfg = RepoConfig(
        areas=["work", "health"],
        contexts=["@computer", "@gym"],
        waiting_stale_days=3,
        sync_auto=False,
    )
    save_repo_config(tmp_path, cfg)
    reloaded = load_repo_config(tmp_path)

    assert reloaded.areas == ["work", "health"]
    assert reloaded.contexts == ["@computer", "@gym"]
    assert reloaded.waiting_stale_days == 3
    assert reloaded.sync_auto is False


def test_partial_file_falls_back_per_section(tmp_path):
    (tmp_path / "config.toml").write_text('[areas]\nvalues = ["solo"]\n')
    cfg = load_repo_config(tmp_path)

    assert cfg.areas == ["solo"]
    assert cfg.contexts == DEFAULT_CONTEXTS  # untouched section keeps its default
    assert cfg.sync_auto is True
