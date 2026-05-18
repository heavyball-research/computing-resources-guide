from pathlib import Path

import pytest

from ccsync.config import find_config, load_config


def write_cfg(d: Path) -> Path:
    p = d / ".ccsync.toml"
    p.write_text(
        """
[remote]
host = "myhost"
path = "/srv/proj"

[sync]
exclude = [".git/", "target/"]
debounce_ms = 250
delete = false

[pull]
paths = ["out/"]
"""
    )
    return p


def test_load_basic(tmp_path: Path):
    write_cfg(tmp_path)
    cfg = load_config(tmp_path)
    assert cfg.remote.host == "myhost"
    assert cfg.remote.path == "/srv/proj"
    assert cfg.sync.exclude == [".git/", "target/"]
    assert cfg.sync.debounce_ms == 250
    assert cfg.sync.delete is False
    assert cfg.pull.paths == ["out/"]
    assert cfg.run.tmux_prefix == "ccs"  # default
    assert cfg.project_root == tmp_path


def test_find_walks_up(tmp_path: Path):
    write_cfg(tmp_path)
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert find_config(sub).parent == tmp_path


def test_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path)


def test_load_with_user_port_identity(tmp_path: Path):
    (tmp_path / ".ccsync.toml").write_text(
        """
[remote]
host = "h"
path = "/p"
user = "ubuntu"
port = 2222
identity_file = "~/.ssh/id_ed25519"
"""
    )
    cfg = load_config(tmp_path)
    assert cfg.remote.user == "ubuntu"
    assert cfg.remote.port == 2222
    assert cfg.remote.identity_file == str(Path("~/.ssh/id_ed25519").expanduser())
    assert cfg.remote.ssh_target == "ubuntu@h"
    assert "-p" in cfg.remote.ssh_opts and "2222" in cfg.remote.ssh_opts
    assert "-i" in cfg.remote.ssh_opts


def test_ssh_target_no_user(tmp_path: Path):
    write_cfg(tmp_path)
    cfg = load_config(tmp_path)
    assert cfg.remote.ssh_target == "myhost"
    assert cfg.remote.ssh_opts == []
    assert cfg.remote.rsync_ssh_arg() == "ssh"


def test_missing_remote_fields(tmp_path: Path):
    (tmp_path / ".ccsync.toml").write_text("[remote]\nhost = \"x\"\n")
    with pytest.raises(ValueError):
        load_config(tmp_path)
