"""Several accounts in one server: configuration, choosing an account, and reading every account.

No mail account or network is needed: the IMAP and SMTP calls are replaced by recorders.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from korean_mail_mcp import imap_client, server, smtp_client
from korean_mail_mcp.accounts import load_accounts
from korean_mail_mcp.models import EmailSummary, Folder, Profile, SearchResult

ONE = {"MAIL_ADDRESS": "a@naver.com", "MAIL_PASSWORD": "pw", "MAIL_FULL_NAME": "A"}
MANY = {
    "MAIL_ACCOUNTS": "naver-a, daum",
    "MAIL_NAVER_A_ADDRESS": "a@naver.com",
    "MAIL_NAVER_A_PASSWORD": "pa",
    "MAIL_NAVER_A_FULL_NAME": "Aaa",
    "MAIL_DAUM_ADDRESS": "d@daum.net",
    "MAIL_DAUM_PASSWORD": "pd",
}

# every tool that is bound to one mailbox or changes one, with arguments that satisfy it
ONE_ACCOUNT_TOOLS = {
    "read_email": {"uid": "1"},
    "read_thread": {"message_id": "<m@example.com>"},
    "create_draft": {"to": ["x@example.com"], "subject": "s", "body": "b"},
    "send_email": {"to": ["x@example.com"], "subject": "s", "body": "b"},
    "download_attachment": {"uid": "1", "part_number": "2"},
    "create_folder": {"name": "Receipts"},
    "move_emails": {"uids": ["1"], "destination": "Receipts"},
    "mark_read": {"uids": ["1"]},
    "trash_emails": {"uids": ["1"]},
}
EACH_ACCOUNT_TOOLS = ("get_profile", "search_emails", "list_folders", "list_drafts")


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key in [key for key in os.environ if key.startswith("MAIL_")]:
        monkeypatch.delenv(key)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


# ---- configuration ----


def test_without_mail_accounts_the_plain_variables_make_one_default_account():
    accounts = load_accounts(ONE)

    assert list(accounts) == ["default"]
    assert (accounts["default"].address, accounts["default"].full_name) == ("a@naver.com", "A")


def test_mail_accounts_reads_one_set_of_variables_per_name_in_order():
    accounts = load_accounts(MANY)

    assert list(accounts) == ["naver-a", "daum"]
    assert accounts["naver-a"].address == "a@naver.com"
    assert accounts["naver-a"].password == "pa"  # noqa: S105 - a dummy test value
    assert accounts["naver-a"].full_name == "Aaa"
    assert accounts["daum"].full_name == ""


def test_plain_variables_are_ignored_when_accounts_are_listed():
    accounts = load_accounts({**MANY, **ONE})

    assert list(accounts) == ["naver-a", "daum"]


def test_blank_mail_accounts_falls_back_to_the_plain_variables():
    assert list(load_accounts({**ONE, "MAIL_ACCOUNTS": "  "})) == ["default"]


def test_mail_accounts_without_a_name_is_an_error():
    with pytest.raises(ValueError, match="lists no account name"):
        load_accounts({**ONE, "MAIL_ACCOUNTS": " , "})


@pytest.mark.parametrize("name", ["1abc", "bad!", "a.b", "x" * 33, "naver a"])
def test_invalid_account_names_are_rejected(name):
    with pytest.raises(ValueError, match="Invalid account name"):
        load_accounts({"MAIL_ACCOUNTS": name})


def test_names_that_read_the_same_variables_are_rejected():
    with pytest.raises(ValueError, match="read the same variables"):
        load_accounts({**MANY, "MAIL_ACCOUNTS": "naver-a,NAVER_A"})


def test_a_missing_variable_names_the_account_and_the_variable():
    env = {key: value for key, value in MANY.items() if key != "MAIL_DAUM_PASSWORD"}

    with pytest.raises(ValueError, match=r"account 'daum': MAIL_DAUM_PASSWORD must be set"):
        load_accounts(env)


def test_missing_plain_variables_keep_their_message():
    with pytest.raises(ValueError, match="MAIL_ADDRESS and MAIL_PASSWORD must be set"):
        load_accounts({})


def test_the_password_stays_out_of_repr():
    assert "pw" not in repr(load_accounts(ONE)["default"])


# ---- choosing an account ----


@pytest.fixture
def calls(monkeypatch):
    """Replace the IMAP and SMTP calls with recorders that note which account they got."""
    log: list[tuple[str, str]] = []

    @contextlib.contextmanager
    def connection(address, password):
        yield address

    def recorder(name):
        def record(conn, *args, **kwargs):
            log.append((name, conn))
            return {"ok": True}

        return record

    def search(conn, **kwargs):
        log.append(("search_emails", conn))
        if conn == "broken@naver.com":
            raise imap_client.AuthenticationError("IMAP authentication failed")
        if conn == "crash@naver.com":
            raise RuntimeError("secret detail that must not reach the model")
        summary = EmailSummary(
            uid="1", subject=f"for {conn}", from_address="x", date="", is_read=False
        )
        return SearchResult(emails=[summary], total_count=1, page=1, page_size=20, has_more=False)

    def returning(name, make):
        def call(conn, *args, **kwargs):
            log.append((name, conn))
            return make(conn)

        return call

    def summary_of(conn):
        return EmailSummary(uid="1", subject=conn, from_address="x", date="", is_read=True)

    shaped = {
        "get_profile": returning("get_profile", lambda c: Profile(c, "", 1, 0)),
        "list_folders": returning("list_folders", lambda c: [Folder("INBOX", "INBOX", 1, 0)]),
        "list_drafts": returning("list_drafts", lambda c: [summary_of(c)]),
        "read_thread": returning("read_thread", lambda c: []),
    }

    def send(address, password, full_name, *args):
        log.append(("send_email", address))
        return {"sent_from": address, "password": password, "full_name": full_name}

    monkeypatch.setattr(imap_client, "imap_connection", connection)
    monkeypatch.setattr(imap_client, "search_emails", search)
    monkeypatch.setattr(smtp_client, "send_email", send)
    for name in (
        "read_email",
        "create_draft",
        "download_attachment",
        "create_folder",
        "move_emails",
        "mark_read",
        "trash_emails",
    ):
        monkeypatch.setattr(imap_client, name, recorder(name))
    for name, fake in shaped.items():
        monkeypatch.setattr(imap_client, name, fake)
    return log


def test_one_account_needs_no_name_and_results_carry_no_account(monkeypatch, calls):
    _set_env(monkeypatch, ONE)

    result = json.loads(server.move_emails(["1"], "Receipts"))

    assert result == {"ok": True}
    assert calls == [("move_emails", "a@naver.com")]


def test_one_account_accepts_its_own_name_and_rejects_another(monkeypatch, calls):
    _set_env(monkeypatch, ONE)

    assert json.loads(server.trash_emails(["1"], account="DEFAULT")) == {"ok": True}
    with pytest.raises(ToolError, match=r"Unknown account 'work'\. Choose one of: default"):
        server.trash_emails(["1"], account="work")


@pytest.mark.parametrize("tool", sorted(ONE_ACCOUNT_TOOLS))
def test_several_accounts_require_a_name_for_tools_bound_to_one_mailbox(monkeypatch, calls, tool):
    _set_env(monkeypatch, MANY)

    with pytest.raises(ToolError, match=r"account is required.*naver-a, daum"):
        getattr(server, tool)(**ONE_ACCOUNT_TOOLS[tool])

    assert calls == []


def test_several_accounts_use_the_named_accounts_credentials_and_name_it_in_the_result(
    monkeypatch, calls
):
    _set_env(monkeypatch, MANY)

    result = json.loads(server.move_emails(["1"], "Receipts", account="Daum"))

    assert result == {"account": "daum", "ok": True}
    assert calls == [("move_emails", "d@daum.net")]


def test_send_email_leaves_from_the_named_account_only(monkeypatch, calls):
    _set_env(monkeypatch, MANY)

    result = json.loads(server.send_email(["x@example.com"], "s", "b", account="naver-a"))

    assert result == {
        "account": "naver-a",
        "sent_from": "a@naver.com",
        "password": "pa",
        "full_name": "Aaa",
    }


def test_an_unknown_account_is_an_error_that_lists_the_names(monkeypatch, calls):
    _set_env(monkeypatch, MANY)

    with pytest.raises(ToolError, match=r"Unknown account 'kakao'\. Choose one of: naver-a, daum"):
        server.trash_emails(["1"], account="kakao")

    assert calls == []


# ---- reading every account ----


def test_reading_without_a_name_runs_on_every_account_in_order(monkeypatch, calls):
    _set_env(monkeypatch, MANY)

    result = json.loads(server.search_emails())

    assert [entry["account"] for entry in result] == ["naver-a", "daum"]
    assert [entry["address"] for entry in result] == ["a@naver.com", "d@daum.net"]
    assert result[1]["result"]["emails"][0]["subject"] == "for d@daum.net"
    assert sorted(calls) == [("search_emails", "a@naver.com"), ("search_emails", "d@daum.net")]


def test_an_unexpected_failure_shows_no_detail_to_the_model(monkeypatch, calls):
    _set_env(monkeypatch, {**MANY, "MAIL_NAVER_A_ADDRESS": "crash@naver.com"})

    result = json.loads(server.search_emails())

    assert result[0]["error"] == "Unexpected error. See the server log."
    assert result[1]["result"]["total_count"] == 1


def test_one_failing_account_reports_an_error_and_does_not_hide_the_others(monkeypatch, calls):
    env = {**MANY, "MAIL_NAVER_A_ADDRESS": "broken@naver.com"}
    _set_env(monkeypatch, env)

    result = json.loads(server.search_emails())

    assert result[0]["error"] == "IMAP authentication failed"
    assert "result" not in result[0]
    assert result[1]["result"]["total_count"] == 1


@pytest.mark.parametrize("tool", EACH_ACCOUNT_TOOLS)
def test_every_read_only_tool_lists_the_accounts_when_none_is_named(monkeypatch, calls, tool):
    _set_env(monkeypatch, MANY)

    result = json.loads(getattr(server, tool)())

    assert [entry["account"] for entry in result] == ["naver-a", "daum"]
    assert all("result" in entry and "error" not in entry for entry in result)


def test_reading_with_a_name_returns_that_accounts_result_with_its_name(monkeypatch, calls):
    _set_env(monkeypatch, MANY)

    result = json.loads(server.search_emails(account="daum"))

    assert result["account"] == "daum"
    assert result["emails"][0]["subject"] == "for d@daum.net"
    assert calls == [("search_emails", "d@daum.net")]


@pytest.mark.parametrize(
    ("tool", "kwargs"),
    [
        ("list_folders", {}),
        ("list_drafts", {}),
        ("read_thread", {"message_id": "<m@example.com>"}),
    ],
)
def test_a_list_result_for_a_named_account_is_wrapped_with_the_account(
    monkeypatch, calls, tool, kwargs
):
    _set_env(monkeypatch, MANY)

    result = json.loads(getattr(server, tool)(account="daum", **kwargs))

    assert set(result) == {"account", "result"}
    assert result["account"] == "daum"
    assert isinstance(result["result"], list)
    assert calls == [(tool, "d@daum.net")]


def test_an_object_result_for_a_named_account_gets_the_account_field(monkeypatch, calls):
    _set_env(monkeypatch, MANY)

    result = json.loads(server.get_profile(account="naver-a"))

    assert result["account"] == "naver-a"
    assert result["email"] == "a@naver.com"


def test_a_list_result_with_one_account_stays_a_plain_list(monkeypatch, calls):
    _set_env(monkeypatch, ONE)

    assert isinstance(json.loads(server.list_folders()), list)


def test_reading_with_one_account_keeps_the_plain_result(monkeypatch, calls):
    _set_env(monkeypatch, ONE)

    result = json.loads(server.search_emails())

    assert "account" not in result
    assert result["total_count"] == 1


# ---- tool list and start-up ----


def test_all_thirteen_tools_take_an_optional_account():
    tools = asyncio.run(server.mcp.list_tools())

    assert len(tools) == 13
    for tool in tools:
        assert "account" in tool.input_schema["properties"], tool.name
        assert "account" not in tool.input_schema.get("required", []), tool.name


def _start(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    clean = {key: value for key, value in os.environ.items() if not key.startswith("MAIL_")}
    return subprocess.run(
        [sys.executable, "-m", "korean_mail_mcp.server"],
        env={**clean, **env},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        input="",
    )


def test_start_up_names_the_account_with_an_unsupported_domain():
    env = {**MANY, "MAIL_DAUM_ADDRESS": "d@example.com"}

    result = _start(env)

    assert result.returncode == 1
    assert "Account 'daum': Unsupported mail domain 'example.com'" in result.stderr


def test_start_up_names_the_variable_that_is_missing():
    env = {key: value for key, value in MANY.items() if key != "MAIL_NAVER_A_PASSWORD"}

    result = _start(env)

    assert result.returncode == 1
    assert "MAIL_NAVER_A_PASSWORD" in result.stderr
