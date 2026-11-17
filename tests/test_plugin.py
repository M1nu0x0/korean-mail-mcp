"""The Claude Code plugin files agree with each other and with the server they start.

No mail account is needed: these read the JSON files under .claude-plugin/ and plugins/, the
version in pyproject.toml and the environment variables server.py reads.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from korean_mail_mcp.accounts import load_accounts

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "korean-mail-mcp"
USER_CONFIG_REF = re.compile(r"\$\{user_config\.(\w+)\}")
# one optional account each, in the order MAIL_ACCOUNTS lists them
SERVICES = ("naver", "daum", "kakao")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pyproject() -> str:
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _server() -> dict:
    return _json(PLUGIN / ".mcp.json")["mcpServers"]["korean-mail"]


def _user_config() -> dict:
    return _json(PLUGIN / ".claude-plugin" / "plugin.json")["userConfig"]


def _environment(**options: str) -> dict[str, str]:
    """The server's environment as Claude Code builds it.

    Each ${user_config.KEY} becomes the value the user gave KEY, or its default when it was left
    out.
    """
    values = {key: option["default"] for key, option in _user_config().items()} | options
    return {
        name: USER_CONFIG_REF.sub(lambda match: values[match.group(1)], value)
        for name, value in _server()["env"].items()
    }


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


def test_the_server_reads_no_variable_the_plugin_has_not_been_checked_against() -> None:
    package = ROOT / "src" / "korean_mail_mcp"
    read = set()
    for name in ("server.py", "accounts.py"):
        source = (package / name).read_text(encoding="utf-8")
        read |= set(re.findall(r'environ\.get\("(\w+)"', source))
    # The plain variables are for servers registered by hand. The plugin lists its accounts in
    # MAIL_ACCOUNTS and fills MAIL_<NAME>_*, which the server builds with an f-string.
    assert read == {"MAIL_ACCOUNTS", "MAIL_ADDRESS", "MAIL_PASSWORD", "MAIL_FULL_NAME"}


def test_server_env_lists_every_service_and_its_three_variables() -> None:
    env = _server()["env"]
    fields = ("ADDRESS", "PASSWORD", "FULL_NAME")
    assert set(env) == {"MAIL_ACCOUNTS"} | {
        f"MAIL_{service.upper()}_{field}" for service in SERVICES for field in fields
    }
    assert env["MAIL_ACCOUNTS"] == ",".join(f"{service}?" for service in SERVICES)


def test_every_user_config_reference_is_declared_and_used() -> None:
    declared = set(_user_config())
    used = {key for value in _server()["env"].values() for key in USER_CONFIG_REF.findall(value)}
    assert used == declared


def test_every_service_has_an_address_option_and_a_sensitive_password_option() -> None:
    user_config = _user_config()
    for service in SERVICES:
        assert not user_config[f"{service}_address"].get("sensitive")
        assert user_config[f"{service}_password"]["sensitive"] is True


def test_no_option_is_required_because_any_service_may_be_left_out() -> None:
    # An option left out reaches the server as its default, an empty string, and the server skips an
    # account whose address is empty. A sensitive option cannot be cleared again, so clearing the
    # address alone has to turn a service off.
    user_config = _user_config()
    assert not any(option.get("required") for option in user_config.values())
    assert all(option.get("default") == "" for option in user_config.values())


def test_the_plugin_environment_gives_one_account_per_filled_service() -> None:
    env = _environment(
        daum_address="d@daum.net",
        daum_password="pd",
        kakao_address="k@kakao.com",
        kakao_password="pk",
        mail_full_name="Kim",
    )

    accounts = load_accounts(env)

    assert list(accounts) == ["daum", "kakao"]
    assert {account.full_name for account in accounts.values()} == {"Kim"}


def test_the_plugin_environment_with_every_option_left_out_is_an_error() -> None:
    with pytest.raises(ValueError, match="No account in MAIL_ACCOUNTS"):
        load_accounts(_environment())
