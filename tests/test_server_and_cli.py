"""The MCP server's tool list and the CLI, without After Effects."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from ae_bridge import cli, server


def test_the_readme_lists_exactly_the_tools_the_server_registers():
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Tools", 1)[1].split("\n## ", 1)[0]
    documented = set(re.findall(r"`([a-z_]+)`", section.split("Addressing:")[0]))

    registered = {t.name for t in asyncio.run(server.mcp.list_tools())}

    assert documented == registered


def test_help_prints_usage(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["ae-bridge", "--help"])
    cli.main()
    assert "ae-bridge ping" in capsys.readouterr().out


def test_an_unknown_command_exits_with_usage(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["ae-bridge", "frobnicate"])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 2
