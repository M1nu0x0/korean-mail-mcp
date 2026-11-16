"""The Claude Code plugin files agree with each other and with the server they start.

No mail account is needed: these read the JSON files under .claude-plugin/ and plugins/, the
version in pyproject.toml and the environment variables server.py reads.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "korean-mail-mcp"
USER_CONFIG_REF = re.compile(r"\$\{user_config\.(\w+)\}")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pyproject() -> str:
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _server() -> dict:
    return _json(PLUGIN / ".mcp.json")["mcpServers"]["korean-mail"]


def test_marketplace_points_at_the_plugin_folder() -> None:
    marketplace = _json(ROOT / ".claude-plugin" / "marketplace.json")
    (entry,) = marketplace["plugins"]
    assert entry["source"] == "./plugins/korean-mail-mcp"
    manifest = _json(ROOT / entry["source"] / ".claude-plugin" / "plugin.json")
    assert manifest["name"] == entry["name"]


def test_plugin_version_matches_pyproject() -> None:
    match = re.search(r'^version = "([^"]+)"', _pyproject(), re.MULTILINE)
    assert match
    assert _json(PLUGIN / ".claude-plugin" / "plugin.json")["version"] == match.group(1)


def test_server_runs_the_console_script_from_this_repository() -> None:
    server = _server()
    repository = _json(PLUGIN / ".claude-plugin" / "plugin.json")["repository"]
    script = re.search(r'^(\S+) = "korean_mail_mcp\.server:main"', _pyproject(), re.MULTILINE)
    assert script
    assert server["command"] == "uvx"
    assert server["args"] == ["--from", f"git+{repository}", script.group(1)]


def test_server_env_is_what_server_py_reads() -> None:
    source = (ROOT / "src" / "korean_mail_mcp" / "server.py").read_text(encoding="utf-8")
    read = set(re.findall(r'os\.environ\.get\("(\w+)"', source))
    assert set(_server()["env"]) == read


def test_every_user_config_reference_is_declared_and_used() -> None:
    declared = set(_json(PLUGIN / ".claude-plugin" / "plugin.json")["userConfig"])
    used = {key for value in _server()["env"].values() for key in USER_CONFIG_REF.findall(value)}
    assert used == declared


def test_required_options_are_the_required_variables() -> None:
    user_config = _json(PLUGIN / ".claude-plugin" / "plugin.json")["userConfig"]
    required = {key for key, option in user_config.items() if option.get("required")}
    assert required == {"mail_address", "mail_password"}
    assert user_config["mail_password"]["sensitive"] is True
