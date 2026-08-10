import pytest
import typer

import bqckup


def test_is_root_user_uses_effective_uid(monkeypatch):
    monkeypatch.setattr(bqckup.os, "geteuid", lambda: 1000)
    assert bqckup.is_root_user() is False

    monkeypatch.setattr(bqckup.os, "geteuid", lambda: 0)
    assert bqckup.is_root_user() is True


def test_require_root_prints_sudo_command_for_non_root(monkeypatch, capsys):
    monkeypatch.setattr(bqckup.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        bqckup.sys,
        "argv",
        ["/usr/bin/bqckup", "run", "--site", "example.com"],
    )

    with pytest.raises(typer.Exit) as error:
        bqckup.require_root()

    assert error.value.exit_code == 1
    assert "sudo bqckup run --site example.com" in capsys.readouterr().out
