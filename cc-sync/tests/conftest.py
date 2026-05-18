from pathlib import Path

import pytest

from ccsync.config import Config, PullCfg, RemoteCfg, RunCfg, SyncCfg


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        project_root=tmp_path,
        remote=RemoteCfg(host="myhost", path="/home/me/proj"),
        sync=SyncCfg(
            exclude=[".git/", "__pycache__/", "*.ncu-rep"],
            debounce_ms=500,
            delete=True,
        ),
        pull=PullCfg(paths=["logs/", "artifacts/"]),
        run=RunCfg(),
    )
