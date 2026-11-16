"""Unit tests that need no mail account or network."""

from __future__ import annotations

import contextlib
import imaplib
import json
import os
import socket
import subprocess
import sys
import threading

import pytest

from korean_mail_mcp import imap_client
from korean_mail_mcp.models import Folder, to_dict
from korean_mail_mcp.providers import hosts_for


@pytest.mark.parametrize("name", ["INBOX", "내게쓴메일함", "R&D", "보낸 메일함/2026"])
def test_mutf7_round_trips_folder_names(name):
    encoded = imap_client.encode_mutf7(name)

    decoded = imap_client.decode_mutf7(encoded)

    assert encoded.isascii()
    assert decoded == name


def test_parse_list_item_reads_flags_and_quoted_name():
    line = b'(\\HasNoChildren \\Drafts) "/" "Drafts"'

    parsed = imap_client._parse_list_item(line)

    assert parsed == ("\\HasNoChildren \\Drafts", "Drafts")


def test_parse_list_item_reads_unquoted_name():
    line = b'(\\HasNoChildren) "/" INBOX'

    parsed = imap_client._parse_list_item(line)

    assert parsed == ("\\HasNoChildren", "INBOX")


def test_parse_list_item_skips_non_bytes_response():
    parsed = imap_client._parse_list_item((b"literal", b"data"))

    assert parsed is None


@pytest.mark.parametrize("folder", ['IN"BOX', "INBOX\r\nA1 DELETE x", "IN\x00BOX"])
def test_sanitize_folder_name_rejects_imap_injection(folder):
    with pytest.raises(ValueError, match="Invalid folder name"):
        imap_client._sanitize_folder_name(folder)


@pytest.mark.parametrize("uid", ["", "1:*", "12 34", "abc"])
def test_sanitize_uid_rejects_non_numeric(uid):
    with pytest.raises(ValueError, match="Invalid UID"):
        imap_client._sanitize_uid(uid)


def test_decode_header_value_decodes_euc_kr_subject():
    raw = "=?EUC-KR?B?vsiz58fPvLy/5A==?="

    decoded = imap_client.decode_header_value(raw)

    assert decoded == "안녕하세요"


def test_to_dict_serializes_dataclass():
    folder = Folder(name="받은메일함", raw_name="INBOX", message_count=3, unseen_count=1)

    result = to_dict(folder)

    assert result == {
        "name": "받은메일함",
        "raw_name": "INBOX",
        "message_count": 3,
        "unseen_count": 1,
    }


def _server_env(**overrides):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MAIL_")}
    env.update(overrides)
    return env


def test_server_exits_with_message_when_credentials_missing():
    result = subprocess.run(
        [sys.executable, "-m", "korean_mail_mcp.server"],
        env=_server_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "MAIL_ADDRESS" in result.stderr


def test_server_lists_tools_over_stdio():
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]

    proc = subprocess.Popen(
        [sys.executable, "-m", "korean_mail_mcp.server"],
        env=_server_env(MAIL_ADDRESS="user@naver.com", MAIL_PASSWORD="dummy"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write("".join(json.dumps(r) + "\n" for r in requests))
        proc.stdin.flush()
        # stdin stays open until the reply arrives: the server stops reading on EOF
        tool_names = set()
        for line in proc.stdout:
            message = json.loads(line)
            if message.get("id") == 2:
                tool_names = {t["name"] for t in message["result"]["tools"]}
                break
        proc.stdin.close()
        proc.wait(timeout=30)
    finally:
        proc.kill()

    assert {
        "search_emails",
        "create_folder",
        "move_emails",
        "mark_read",
        "trash_emails",
    } <= tool_names


def test_server_exits_when_mail_domain_is_unsupported():
    result = subprocess.run(
        [sys.executable, "-m", "korean_mail_mcp.server"],
        env=_server_env(MAIL_ADDRESS="user@example.com", MAIL_PASSWORD="dummy"),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "Unsupported mail domain 'example.com'" in result.stderr


@pytest.mark.parametrize(
    ("address", "hosts"),
    [
        ("me@naver.com", ("imap.naver.com", "smtp.naver.com")),
        ("me@daum.net", ("imap.daum.net", "smtp.daum.net")),
        ("me@hanmail.net", ("imap.daum.net", "smtp.daum.net")),
        ("Me@Kakao.com", ("imap.kakao.com", "smtp.kakao.com")),
    ],
)
def test_hosts_for_picks_servers_by_email_domain(address, hosts):
    assert hosts_for(address) == hosts


def test_mailbox_passes_raw_names_and_encodes_display_names():
    assert imap_client._mailbox("&yBXCwA-") == '"&yBXCwA-"'
    assert imap_client._mailbox("영수증") == f'"{imap_client.encode_mutf7("영수증")}"'


@pytest.mark.parametrize("uids", [[], ["1:*"], ["1", "2 3"], ["1"] * 501])
def test_uid_set_rejects_empty_oversized_and_non_numeric(uids):
    with pytest.raises(ValueError, match=r"UID|uids"):
        imap_client._uid_set(uids)


# UID 7's subject is "회의 일정 안내" as an RFC 2047 encoded word, the way servers store it
SEARCH_HEADERS = {
    7: b"From: Hong Gildong <hong@example.com>\r\n"
    b"Subject: =?UTF-8?B?7ZqM7J2YIOydvOyglSDslYjrgrQ=?=\r\n\r\n",
    9: b"From: Lee <lee@example.com>\r\nSubject: Weekly Report\r\n\r\n",
}


@pytest.fixture
def imap():
    """A real imaplib client talking to a local server that records each command."""
    server = socket.create_server(("127.0.0.1", 0))
    commands = []

    def serve():
        sock, _ = server.accept()
        with sock, sock.makefile("rb") as reader:
            sock.sendall(b"* OK ready\r\n")
            for raw in reader:
                tag, _, command = raw.rstrip(b"\r\n").partition(b" ")
                commands.append(command)
                if command.startswith(b"CAPABILITY"):
                    sock.sendall(b"* CAPABILITY IMAP4rev1\r\n")
                if b"SEARCH" in command:
                    sock.sendall(b"* SEARCH 7 9\r\n")
                if b"HEADER.FIELDS (FROM TO SUBJECT)" in command:
                    for seq, (uid, headers) in enumerate(SEARCH_HEADERS.items(), start=1):
                        item = b"BODY[HEADER.FIELDS (FROM TO SUBJECT)]"
                        sock.sendall(
                            b"* %d FETCH (UID %d %s {%d}\r\n" % (seq, uid, item, len(headers))
                        )
                        sock.sendall(headers + b")\r\n")
                if command.startswith(b"LIST"):
                    sock.sendall(b'* LIST (\\HasNoChildren \\Trash) "/" "Deleted Messages"\r\n')
                sock.sendall(tag + b" OK done\r\n")

    threading.Thread(target=serve, daemon=True).start()
    conn = imaplib.IMAP4("127.0.0.1", server.getsockname()[1], timeout=10)
    conn.login("user", "pass")
    commands.clear()
    yield conn, commands
    with contextlib.suppress(Exception):
        conn.logout()
    server.close()


def test_move_emails_selects_source_and_moves_to_encoded_destination(imap):
    conn, commands = imap

    imap_client.move_emails(conn, ["3", "5"], "영수증", folder="INBOX")

    destination = imap_client.encode_mutf7("영수증").encode()
    assert commands == [b'SELECT "INBOX"', b'UID MOVE 3,5 "' + destination + b'"']


def test_mark_read_clears_seen_flag_when_read_is_false(imap):
    conn, commands = imap

    imap_client.mark_read(conn, ["4"], read=False)

    assert commands[-1] == b"UID STORE 4 -FLAGS.SILENT (\\Seen)"


def test_trash_emails_moves_to_folder_flagged_as_trash(imap):
    conn, commands = imap

    imap_client.trash_emails(conn, ["8"])

    assert commands[-1] == b'UID MOVE 8 "Deleted Messages"'


def test_create_folder_encodes_korean_name(imap):
    conn, commands = imap

    imap_client.create_folder(conn, "영수증")

    assert commands == [b'CREATE "' + imap_client.encode_mutf7("영수증").encode() + b'"']


def test_read_email_fetches_the_message_with_body_peek(imap):
    conn, commands = imap

    with pytest.raises(imap_client.EmailNotFoundError):
        imap_client.read_email(conn, "5")

    assert commands[-1] == b"UID FETCH 5 (FLAGS BODY.PEEK[])"


def test_download_attachment_fetches_the_message_with_body_peek(imap):
    conn, commands = imap

    with pytest.raises(imap_client.EmailNotFoundError):
        imap_client.download_attachment(conn, "5", "2")

    assert commands[-1] == b"UID FETCH 5 (BODY.PEEK[])"


def test_build_search_criteria_leaves_text_filters_to_the_client():
    assert imap_client._build_search_criteria("01-Jan-2026", None, False) == [
        "SINCE",
        "01-Jan-2026",
        "UNSEEN",
    ]


def test_build_search_criteria_matches_all_without_filters():
    assert imap_client._build_search_criteria(None, None, None) == ["ALL"]


@pytest.mark.parametrize("date", ["2026-01-01", "01-Jan-2026 OR ALL", "1-jan-2026"])
def test_build_search_criteria_rejects_malformed_dates(date):
    with pytest.raises(ValueError, match="Invalid date"):
        imap_client._build_search_criteria(date, None, None)


def test_search_emails_matches_korean_subject_on_decoded_headers(imap):
    conn, commands = imap

    result = imap_client.search_emails(conn, subject="일정")

    assert commands[:3] == [
        b'EXAMINE "INBOX"',
        b"UID SEARCH ALL",
        b"UID FETCH 7:9 (UID BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT)])",
    ]
    assert result.total_count == 1


def test_search_emails_matches_text_ignoring_case(imap):
    conn, _ = imap

    result = imap_client.search_emails(conn, sender="LEE", subject="weekly report")

    assert result.total_count == 1


def test_search_emails_requires_every_text_filter_to_match(imap):
    conn, _ = imap

    result = imap_client.search_emails(conn, sender="Lee", subject="일정")

    assert result.total_count == 0


def test_search_emails_skips_header_fetch_without_text_filters(imap):
    conn, commands = imap

    result = imap_client.search_emails(conn, is_read=False)

    assert b"UID SEARCH UNSEEN" in commands
    assert not any(b"FROM TO SUBJECT" in c for c in commands)
    assert result.total_count == 2
