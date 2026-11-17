"""Unit tests that need no mail account or network."""

from __future__ import annotations

import base64
import contextlib
import email
import email.policy
import email.utils
import imaplib
import json
import os
import smtplib
import socket
import subprocess
import sys
import threading
import time
import unicodedata
from email.message import EmailMessage
from types import SimpleNamespace
from typing import cast

import pytest

from korean_mail_mcp import imap_client, server, smtp_client
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


@pytest.mark.parametrize("date", ["not a date", "Mon, 32 Foo 2026 99:99:99 +0900"])
def test_parse_date_returns_empty_for_malformed_dates(date):
    assert imap_client._parse_date(date) == ""


def test_parse_address_list_keeps_commas_inside_display_names():
    header = '"Hong, Gildong" <hong@example.com>, =?UTF-8?B?7J2066aE?= <lee@example.com>, x@y.com'

    addresses = imap_client._parse_address_list(header)

    assert addresses == ["Hong, Gildong <hong@example.com>", "이름 <lee@example.com>", "x@y.com"]


@pytest.mark.parametrize("uid", ["²", "١٢٣"])
def test_sanitize_uid_rejects_unicode_digits(uid):
    with pytest.raises(ValueError, match="Invalid UID"):
        imap_client._sanitize_uid(uid)


@pytest.mark.parametrize("raw", ["&", "&ABC", "&!!!-"])
def test_decode_mutf7_returns_malformed_names_unchanged(raw):
    assert imap_client.decode_mutf7(raw) == raw


def test_mailbox_encodes_ascii_names_that_are_not_modified_utf7():
    assert imap_client._mailbox("R&D") == '"R&-D"'
    assert imap_client._mailbox("R&-D") == '"R&-D"'


def test_read_thread_escapes_backslashes_in_message_id(imap):
    conn, commands = imap

    imap_client.read_thread(conn, "<a\\b@example.com>")

    assert commands[1] == b'UID SEARCH HEADER Message-ID "<a\\\\b@example.com>"'


def test_read_thread_sends_one_ored_search_per_message_id(imap):
    conn, commands = imap

    imap_client.read_thread(conn, "<m@example.com>")

    searches = [c for c in commands if c.startswith(b"UID SEARCH")]
    expected = (
        b'UID SEARCH OR OR HEADER Message-ID "<m@example.com>" HEADER References '
        b'"<m@example.com>" HEADER In-Reply-To "<m@example.com>"'
    )
    assert searches[1:] == [expected]


def test_read_thread_searches_each_header_apart_where_ored_headers_find_nothing(imap, monkeypatch):
    conn, commands = imap
    monkeypatch.setattr(imap_client, "SERVER_TEXT_SEARCH_HOSTS", {conn.host})

    imap_client.read_thread(conn, "<m@example.com>")

    searches = [c for c in commands if c.startswith(b"UID SEARCH")]
    assert searches[1:] == [
        b'UID SEARCH HEADER Message-ID "<m@example.com>"',
        b'UID SEARCH HEADER References "<m@example.com>"',
        b'UID SEARCH HEADER In-Reply-To "<m@example.com>"',
    ]


def test_read_thread_rejects_non_ascii_message_id(imap):
    conn, _ = imap

    with pytest.raises(ValueError, match="Invalid Message-ID"):
        imap_client.read_thread(conn, "<메일@example.com>")


class _OneMessage:
    def __init__(self, raw: bytes):
        self.raw = raw

    def select(self, *args, **kwargs):
        return "OK", [b"1"]

    def uid(self, *args):
        return "OK", [(b"1 (UID 5 FLAGS () BODY[] {%d}" % len(self.raw), self.raw), b")"]


def test_read_email_lists_inline_parts_with_a_filename_as_attachments():
    raw = (
        b'Content-Type: multipart/related; boundary="b"\r\n\r\n'
        b"--b\r\nContent-Type: text/plain\r\n\r\nhello\r\n"
        b"--b\r\nContent-Type: image/png\r\nContent-Disposition: inline; filename=a.png\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\niVBORw==\r\n"
        b"--b--\r\n"
    )

    mail = imap_client.read_email(_OneMessage(raw), "5")  # type: ignore[arg-type]

    assert mail.body_text.strip() == "hello"
    assert [(a.filename, a.part_number) for a in mail.attachments] == [("a.png", "3")]


def test_read_email_lists_an_attached_eml_file():
    raw = (
        b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n'
        b"--b\r\nContent-Type: text/plain\r\n\r\nsee attached\r\n"
        b"--b\r\nContent-Type: message/rfc822\r\n"
        b'Content-Disposition: attachment; filename="fwd.eml"\r\n\r\n'
        b"Subject: inner\r\nContent-Type: text/plain\r\n\r\ninner body\r\n"
        b"--b--\r\n"
    )

    mail = imap_client.read_email(_OneMessage(raw), "5")  # type: ignore[arg-type]

    assert mail.body_text.strip() == "see attached"
    assert [(a.filename, a.content_type) for a in mail.attachments] == [
        ("fwd.eml", "message/rfc822")
    ]
    assert mail.attachments[0].size > 0


def test_download_attachment_returns_the_content_of_an_attached_eml_file():
    raw = (
        b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n'
        b"--b\r\nContent-Type: text/plain\r\n\r\nsee attached\r\n"
        b"--b\r\nContent-Type: message/rfc822\r\n"
        b'Content-Disposition: attachment; filename="fwd.eml"\r\n\r\n'
        b"Subject: inner\r\nContent-Type: text/plain\r\n\r\ninner body\r\n"
        b"--b--\r\n"
    )
    conn = _OneMessage(raw)

    part_number = imap_client.read_email(conn, "5").attachments[0].part_number  # type: ignore[arg-type]
    result = imap_client.download_attachment(conn, "5", part_number)  # type: ignore[arg-type]

    content = base64.b64decode(result.content_base64)
    assert result.filename == "fwd.eml"
    assert result.content_type == "message/rfc822"
    assert result.size == len(content) > 0
    inner = email.message_from_bytes(content)
    assert inner["Subject"] == "inner"
    assert cast(str, inner.get_payload()).strip() == "inner body"


def test_read_email_keeps_a_body_part_that_only_has_a_content_type_name():
    raw = b'Content-Type: text/plain; name="memo.txt"; charset=utf-8\r\n\r\nbody text\r\n'

    mail = imap_client.read_email(_OneMessage(raw), "5")  # type: ignore[arg-type]

    assert mail.body_text.strip() == "body text"
    assert mail.attachments == []


def test_send_email_quotes_a_display_name_with_a_comma(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, *args):
            pass

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", FakeSMTP)

    smtp_client.send_email("me@naver.com", "pw", "Hong, Gildong", ["a@example.com"], "s", "b")

    assert str(sent[0]["From"]) == '"Hong, Gildong" <me@naver.com>'


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


def test_search_emails_searches_on_the_server_where_it_matches_decoded_headers(imap, monkeypatch):
    conn, commands = imap
    monkeypatch.setattr(imap_client, "SERVER_TEXT_SEARCH_HOSTS", {conn.host})

    result = imap_client.search_emails(conn, subject="회의 일정", is_read=False)

    expected = 'UID SEARCH CHARSET UTF-8 UNSEEN SUBJECT "회의 일정"'.encode()
    assert commands[1] == expected
    assert not any(b"FROM TO SUBJECT" in c for c in commands)
    assert result.total_count == 2


def _subject(raw: bytes):
    return email.message_from_bytes(b"Subject: " + raw + b"\r\n\r\n")


def _encoded_word(text: str, charset: str = "utf-8") -> bytes:
    return b"=?" + charset.encode() + b"?B?" + base64.b64encode(text.encode(charset)) + b"?="


MEETING = "회의 일정 안내"


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        pytest.param(_encoded_word(MEETING), "일정", id="utf-8 base64"),
        pytest.param(_encoded_word(MEETING, "euc-kr"), "일정", id="euc-kr base64"),
        pytest.param(
            b"=?ks_c_5601-1987?B?" + base64.b64encode(MEETING.encode("euc-kr")) + b"?=",
            "일정",
            id="ks_c_5601-1987 label",
        ),
        pytest.param(MEETING.encode("euc-kr"), "일정", id="raw euc-kr bytes without encoded-word"),
        pytest.param(
            _encoded_word("회의 일") + b"\r\n " + _encoded_word("정 안내"),
            "일정",
            id="word split across two encoded-words",
        ),
        pytest.param(
            b"=?UTF-8?B?" + base64.b64encode(MEETING.encode("euc-kr")) + b"?=",
            "일정",
            id="euc-kr bytes mislabelled as utf-8",
        ),
        pytest.param(b"Weekly\r\n Report", "weekly report", id="phrase across a folded line"),
        pytest.param(
            _encoded_word(unicodedata.normalize("NFD", MEETING)),
            "일정",
            id="decomposed Hangul in the subject",
        ),
        pytest.param(
            _encoded_word(MEETING),
            unicodedata.normalize("NFD", "일정"),
            id="decomposed Hangul in the search text",
        ),
        pytest.param(_encoded_word("ＡＢＣ 안내"), "abc", id="full-width letters"),  # noqa: RUF001
        pytest.param(_encoded_word("회의  일정"), "회의 일정", id="repeated spaces"),
        pytest.param(b"=?UTF-8?B?7ZqM7J2Y!!!?= report", "report", id="malformed encoded-word"),
    ],
)
def test_headers_match_finds_text_however_the_subject_is_stored(raw, needle):
    assert imap_client._headers_match(_subject(raw), {"Subject": needle})


def test_headers_match_rejects_text_that_is_absent():
    assert not imap_client._headers_match(_subject(_encoded_word(MEETING)), {"Subject": "결제"})


def test_search_emails_ignores_blank_text_filters(imap):
    conn, commands = imap

    result = imap_client.search_emails(conn, subject="   ")

    assert not any(b"FROM TO SUBJECT" in c for c in commands)
    assert result.total_count == 2


@pytest.mark.parametrize("charset", ["utf-8", "euc-kr"])
@pytest.mark.parametrize("prefix", ["", "A", "AB", "가", "가A", "[공지] "])
def test_encoded_forms_occur_in_base64_subjects_at_every_alignment(charset, prefix):
    stored = base64.b64encode(f"{prefix}안내 드립니다".encode(charset))

    forms = imap_client._encoded_forms("안내")

    assert any(form in stored for form in forms)


@pytest.mark.parametrize("space", [b"_", b"=20"])
def test_encoded_forms_occur_in_quoted_printable_subjects(space):
    stored = b"=ED=9A=8C=EC=9D=98" + space + b"=EC=9D=BC=EC=A0=95"

    forms = imap_client._encoded_forms("회의 일정")

    assert stored in forms


def test_encoded_forms_keep_ascii_text_as_it_is():
    assert imap_client._encoded_forms("Weekly Report") == [b"Weekly Report"]


def test_search_emails_server_mode_searches_encoded_forms_on_raw_matching_servers(imap):
    conn, commands = imap

    result = imap_client.search_emails(conn, subject="안내", text_search="server")

    search = commands[1]
    assert search.startswith(b"UID SEARCH OR OR ")
    assert b'SUBJECT "7JWI64K0"' in search
    assert b'SUBJECT "=EC=95=88=EB=82=B4"' in search
    assert not any(b"FROM TO SUBJECT" in c for c in commands)
    assert result.total_count == 2


def test_search_emails_local_mode_overrides_server_search(imap, monkeypatch):
    conn, commands = imap
    monkeypatch.setattr(imap_client, "SERVER_TEXT_SEARCH_HOSTS", {conn.host})

    result = imap_client.search_emails(conn, subject="일정", text_search="local")

    assert commands[1] == b"UID SEARCH ALL"
    assert result.total_count == 1


def test_search_emails_rejects_unknown_text_search_mode(imap):
    conn, _ = imap

    with pytest.raises(ValueError, match="text_search"):
        imap_client.search_emails(conn, subject="a", text_search="fuzzy")


def test_casings_cover_every_mix_of_upper_and_lower_case():
    casings = imap_client._casings("git")

    assert sorted(casings) == sorted(["git", "giT", "gIt", "gIT", "Git", "GiT", "GIt", "GIT"])


def test_casings_leave_text_without_case_alone():
    assert imap_client._casings("안내 2026") == ["안내 2026"]


def test_text_criteria_ors_all_casings_of_a_short_text():
    criteria, needs_check = imap_client._text_criteria({"Subject": "github"})

    assert criteria.count("OR") == 63
    assert b'"GitHub"' in criteria
    assert not needs_check


def test_text_criteria_sends_one_term_for_korean_text():
    criteria, needs_check = imap_client._text_criteria({"From": "네이버"})

    assert criteria == ["FROM", '"네이버"'.encode()]
    assert not needs_check


def test_text_criteria_cuts_a_long_text_into_pieces_and_asks_for_a_check():
    criteria, needs_check = imap_client._text_criteria({"Subject": "weekly report"})

    assert b'"weekly r"' in criteria
    assert b'"eport"' in criteria
    assert needs_check


def test_text_criteria_sends_at_most_three_pieces_of_a_very_long_text():
    criteria, _ = imap_client._text_criteria({"Subject": "a" * 40})

    assert criteria.count("OR") == 3 * 127


def test_text_criteria_escapes_quotes_and_rejects_line_breaks():
    criteria, _ = imap_client._text_criteria({"Subject": 'A "B"'})

    assert b'"A \\"B\\""' in criteria
    with pytest.raises(ValueError, match="prohibited"):
        imap_client._text_criteria({"Subject": "a\r\nA1 LOGOUT"})


def test_search_emails_checks_only_the_server_hits_for_a_long_text(imap, monkeypatch):
    conn, commands = imap
    monkeypatch.setattr(imap_client, "SERVER_TEXT_SEARCH_HOSTS", {conn.host})

    result = imap_client.search_emails(conn, subject="weekly report")

    assert commands[1].startswith(b"UID SEARCH OR ")
    assert commands[2] == b"UID FETCH 7,9 (UID BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT)])"
    assert result.total_count == 1


def test_search_emails_trusts_the_server_hits_for_a_short_text(imap, monkeypatch):
    conn, commands = imap
    monkeypatch.setattr(imap_client, "SERVER_TEXT_SEARCH_HOSTS", {conn.host})

    result = imap_client.search_emails(conn, subject="weekly")

    assert not any(b"FROM TO SUBJECT" in c for c in commands)
    assert result.total_count == 2


def test_text_criteria_keeps_all_fields_within_the_measured_term_limit():
    wanted = {"From": "a" * 40, "To": "b" * 40, "Subject": "c" * 40}

    criteria, needs_check = imap_client._text_criteria(wanted)

    terms = sum(1 for c in criteria if c in ("FROM", "TO", "SUBJECT"))
    assert terms <= imap_client.MAX_SERVER_TERMS
    # every field still sends its first piece, and the rest is left to the local check
    assert {"FROM", "TO", "SUBJECT"} <= set(criteria)
    assert needs_check


class _HeaderConn:
    """Answers each header FETCH with the UIDs it is scripted to return, and records the sets."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.uid_sets = []

    def uid(self, command, uid_set, items):
        self.uid_sets.append(uid_set)
        data = []
        for uid in self.answers.pop(0):
            headers = b"Subject: Weekly Report\r\n\r\n"
            item = b"BODY[HEADER.FIELDS (FROM TO SUBJECT)]"
            data.append((b"1 (UID %d %s {%d}" % (uid, item, len(headers)), headers))
            data.append(b")")
        return "OK", data


def _filter(conn, uids, sparse=False):
    return imap_client._filter_by_headers(
        cast(imaplib.IMAP4_SSL, conn), uids, {"Subject": "weekly"}, sparse=sparse
    )


def test_filter_by_headers_asks_again_for_uids_the_server_left_out():
    conn = _HeaderConn([[7, 9], [8]])

    assert _filter(conn, [b"7", b"8", b"9"]) == [b"7", b"8", b"9"]
    assert conn.uid_sets == ["7:9", "8"]


def test_filter_by_headers_gives_up_on_a_uid_still_missing_after_the_retry():
    conn = _HeaderConn([[7, 9], []])

    assert _filter(conn, [b"7", b"8", b"9"]) == [b"7", b"9"]
    assert conn.uid_sets == ["7:9", "8"]


def test_filter_by_headers_does_not_retry_when_every_uid_was_answered():
    conn = _HeaderConn([[7, 9]])

    assert _filter(conn, [b"7", b"9"], sparse=True) == [b"7", b"9"]
    assert conn.uid_sets == ["7,9"]


def test_filter_by_headers_retries_in_small_batches(monkeypatch):
    monkeypatch.setattr(imap_client, "HEADER_RETRY_BATCH", 2)
    conn = _HeaderConn([[], [1, 2], [3]])

    assert _filter(conn, [b"1", b"2", b"3"], sparse=True) == [b"1", b"2", b"3"]
    assert conn.uid_sets == ["1,2,3", "1,2", "3"]


# ---- input validation ----


@pytest.mark.parametrize("value", ["a\r\nBcc: x@example.com", "a\nb", "a\rb"])
def test_sanitize_header_value_rejects_line_breaks(value):
    with pytest.raises(ValueError, match="CRLF"):
        imap_client._sanitize_header_value(value)


def test_sanitize_header_value_keeps_a_single_line_value():
    value = "홍 길동 <gildong@example.com>"

    result = imap_client._sanitize_header_value(value)

    assert result == value


@pytest.mark.parametrize("body_type", ["", "text/xml", "TEXT/PLAIN"])
def test_validate_body_type_rejects_types_outside_the_allow_list(body_type):
    with pytest.raises(ValueError, match="body_type must be one of"):
        imap_client._validate_body_type(body_type)


@pytest.mark.parametrize("body_type", ["text/plain", "text/html"])
def test_validate_body_type_accepts_allowed_types(body_type):
    result = imap_client._validate_body_type(body_type)

    assert result == body_type


@pytest.mark.parametrize("page", [0, -1])
def test_validate_pagination_rejects_a_page_below_one(page):
    with pytest.raises(ValueError, match="page must be >= 1"):
        imap_client._validate_pagination(page, 10)


@pytest.mark.parametrize("page_size", [0, -5, imap_client.MAX_PAGE_SIZE + 1])
def test_validate_pagination_rejects_a_page_size_out_of_range(page_size):
    with pytest.raises(ValueError, match="page_size must be between"):
        imap_client._validate_pagination(1, page_size)


@pytest.mark.parametrize(("page", "page_size"), [(1, 1), (3, imap_client.MAX_PAGE_SIZE)])
def test_validate_pagination_returns_values_inside_the_bounds(page, page_size):
    result = imap_client._validate_pagination(page, page_size)

    assert result == (page, page_size)


def test_hosts_for_rejects_an_unsupported_domain():
    with pytest.raises(ValueError, match=r"Unsupported mail domain 'example\.com'"):
        hosts_for("me@example.com")


# ---- scripted IMAP connection ----


class _FakeConn:
    """An IMAP connection with scripted replies, recording every call it receives.

    A reply is returned as it is, called with the arguments when it is a function, or
    raised when it is an exception.
    """

    def __init__(self, **replies):
        self.replies = replies
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, *args))
            reply = self.replies[name]
            if isinstance(reply, Exception):
                raise reply
            return reply(*args) if callable(reply) else reply

        return method


def _imap(conn: object) -> imaplib.IMAP4_SSL:
    return cast(imaplib.IMAP4_SSL, conn)


DRAFTS_LIST = ("OK", [b'(\\HasNoChildren \\Drafts) "/" "Drafts"'])
SUMMARY_HEADER = (
    b"From: Hong Gildong <hong@example.com>\r\n"
    b"Subject: =?UTF-8?B?7ZqM7J2YIOydvOyglSDslYjrgrQ=?=\r\n"
    b"Date: Mon, 16 Nov 2026 16:51:00 +0900\r\n\r\n"
)


def _summary_reply(uid, flags, header=SUMMARY_HEADER):
    meta = b"1 (UID %d FLAGS (%s) BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {%d}" % (
        uid,
        flags,
        len(header),
    )
    return "OK", [(meta, header), b")"]


# ---- connection ----


@pytest.fixture
def ssl_client(monkeypatch):
    """Replace imaplib.IMAP4_SSL with a fake that logs each step and can be made to fail."""
    state = SimpleNamespace(log=[], connect_error=None, login_error=None)

    class FakeSSL:
        def __init__(self, host, port, timeout):
            if state.connect_error:
                raise state.connect_error
            state.log.append(("connect", host, port, timeout))

        def login(self, user, password):
            state.log.append(("login", user, password))
            if state.login_error:
                raise state.login_error

        def logout(self):
            state.log.append(("logout",))

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", FakeSSL)
    return state


def _use_connection(address, error=None):
    """Open a connection and leave it at once, raising error inside the block when given."""
    with imap_client.imap_connection(address, "pw"):
        if error:
            raise error


def test_imap_connection_logs_in_to_the_provider_host_and_logs_out_on_exit(ssl_client):
    _use_connection("me@naver.com")

    assert ssl_client.log == [
        ("connect", "imap.naver.com", 993, 30),
        ("login", "me@naver.com", "pw"),
        ("logout",),
    ]


def test_imap_connection_logs_out_when_the_body_raises(ssl_client):
    with pytest.raises(RuntimeError, match="boom"):
        _use_connection("me@naver.com", RuntimeError("boom"))

    assert ssl_client.log[-1] == ("logout",)


def test_imap_connection_wraps_a_connect_failure_with_the_host(ssl_client):
    ssl_client.connect_error = OSError("timed out")

    with pytest.raises(imap_client.MailConnectionError, match=r"imap\.daum\.net:993") as error:
        _use_connection("me@daum.net")

    assert isinstance(error.value.__cause__, OSError)
    assert ssl_client.log == []


def test_imap_connection_hides_the_server_text_when_login_fails(ssl_client):
    ssl_client.login_error = imaplib.IMAP4.error("[AUTHENTICATIONFAILED] wrong secret")

    with pytest.raises(imap_client.AuthenticationError) as error:
        _use_connection("me@kakao.com")

    assert "AUTHENTICATIONFAILED" not in str(error.value)
    assert "app password" in str(error.value)
    assert ssl_client.log[-1] == ("logout",)


def test_imap_connection_rejects_an_unsupported_domain_before_connecting(ssl_client):
    with pytest.raises(ValueError, match="Unsupported mail domain"):
        _use_connection("me@example.com")

    assert ssl_client.log == []


# ---- profile and folders ----


def test_get_profile_counts_total_and_unseen_messages():
    conn = _FakeConn(select=("OK", [b"42"]), search=("OK", [b"3 8 9"]))

    profile = imap_client.get_profile(_imap(conn), "me@naver.com", "홍길동")

    assert to_dict(profile) == {
        "email": "me@naver.com",
        "full_name": "홍길동",
        "total_messages": 42,
        "unseen_messages": 3,
    }


def test_get_profile_counts_zero_for_an_empty_mailbox():
    conn = _FakeConn(select=("OK", [None]), search=("OK", [b""]))

    profile = imap_client.get_profile(_imap(conn), "me@naver.com", "")

    assert (profile.total_messages, profile.unseen_messages) == (0, 0)


@pytest.mark.parametrize(
    ("replies", "message"),
    [
        ({"select": ("NO", [b"denied"]), "search": ("OK", [b""])}, "Failed to select INBOX"),
        ({"select": ("OK", [b"1"]), "search": ("NO", [b"denied"])}, "unseen messages"),
    ],
)
def test_get_profile_raises_when_the_server_refuses(replies, message):
    conn = _FakeConn(**replies)

    with pytest.raises(imap_client.MailIMAPError, match=message):
        imap_client.get_profile(_imap(conn), "me@naver.com", "")


def test_list_folders_decodes_display_names_and_reads_counts():
    korean = imap_client.encode_mutf7("영수증")
    counts = {
        '"INBOX"': b"INBOX (MESSAGES 5 UNSEEN 2)",
        f'"{korean}"': b"folder (MESSAGES 12 UNSEEN 0)",
    }
    conn = _FakeConn(
        list=(
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                (b"literal", b"skipped"),
                f'(\\HasNoChildren) "/" "{korean}"'.encode(),
            ],
        ),
        status=lambda mailbox, items: ("OK", [counts[mailbox]]),
    )

    folders = imap_client.list_folders(_imap(conn))

    assert [to_dict(f) for f in folders] == [
        {"name": "INBOX", "raw_name": "INBOX", "message_count": 5, "unseen_count": 2},
        {"name": "영수증", "raw_name": korean, "message_count": 12, "unseen_count": 0},
    ]


def test_list_folders_reports_zero_counts_when_status_fails():
    conn = _FakeConn(
        list=("OK", [b'(\\HasNoChildren) "/" "Archive"']),
        status=imaplib.IMAP4.error("STATUS failed"),
    )

    folders = imap_client.list_folders(_imap(conn))

    assert [(f.name, f.message_count, f.unseen_count) for f in folders] == [("Archive", 0, 0)]


def test_list_folders_raises_when_the_server_refuses_to_list():
    conn = _FakeConn(list=("NO", [b"denied"]))

    with pytest.raises(imap_client.MailIMAPError, match="Failed to list folders"):
        imap_client.list_folders(_imap(conn))


def test_find_drafts_folder_prefers_the_special_use_attribute_over_names():
    conn = _FakeConn(
        list=(
            "OK",
            [
                (b"literal", b"skipped"),
                b'(\\HasNoChildren) "/" "Drafts"',
                b'(\\HasNoChildren \\Drafts) "/" "Mine"',
            ],
        )
    )

    folder = imap_client._find_drafts_folder(_imap(conn))

    assert folder == "Mine"


def test_find_drafts_folder_falls_back_to_a_known_name_ignoring_case():
    conn = _FakeConn(
        list=("OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "DRAFTS"'])
    )

    folder = imap_client._find_drafts_folder(_imap(conn))

    assert folder == "DRAFTS"


def test_find_drafts_folder_matches_a_korean_name_stored_as_modified_utf7():
    raw = imap_client.encode_mutf7("임시보관함")
    conn = _FakeConn(list=("OK", [f'(\\HasNoChildren) "/" "{raw}"'.encode()]))

    folder = imap_client._find_drafts_folder(_imap(conn))

    assert folder == raw


def test_find_drafts_folder_raises_when_no_folder_matches():
    conn = _FakeConn(list=("OK", [b'(\\HasNoChildren) "/" "INBOX"']))

    with pytest.raises(imap_client.FolderNotFoundError, match="Could not find folder with role"):
        imap_client._find_drafts_folder(_imap(conn))


def test_find_drafts_folder_raises_when_the_server_refuses_to_list():
    conn = _FakeConn(list=("NO", [b"denied"]))

    with pytest.raises(imap_client.MailIMAPError, match="Failed to list folders"):
        imap_client._find_drafts_folder(_imap(conn))


# ---- drafts ----


def test_fetch_email_summary_reads_subject_sender_date_and_seen_flag():
    conn = _FakeConn(uid=_summary_reply(5, b"\\Seen"))

    summary = imap_client._fetch_email_summary(_imap(conn), b"5")

    assert summary is not None
    assert to_dict(summary) == {
        "uid": "5",
        "subject": "회의 일정 안내",
        "from_address": "Hong Gildong <hong@example.com>",
        "date": "2026-11-16T16:51:00+09:00",
        "is_read": True,
    }
    assert conn.calls == [
        ("uid", "FETCH", "5", "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
    ]


def test_fetch_email_summary_marks_a_message_without_the_seen_flag_as_unread():
    conn = _FakeConn(uid=_summary_reply(5, b""))

    summary = imap_client._fetch_email_summary(_imap(conn), b"5")

    assert summary is not None
    assert summary.is_read is False


@pytest.mark.parametrize("reply", [("NO", [b"denied"]), ("OK", [None]), ("OK", [])])
def test_fetch_email_summary_returns_none_when_nothing_comes_back(reply):
    conn = _FakeConn(uid=reply)

    summary = imap_client._fetch_email_summary(_imap(conn), b"5")

    assert summary is None


def test_list_drafts_returns_the_newest_draft_first():
    def uid(command, *args):
        if command == "SEARCH":
            return "OK", [b"1 2"]
        return _summary_reply(int(args[0]), b"")

    conn = _FakeConn(list=DRAFTS_LIST, select=("OK", [b"2"]), uid=uid)

    drafts = imap_client.list_drafts(_imap(conn))

    assert [d.uid for d in drafts] == ["2", "1"]
    assert ("select", '"Drafts"') in conn.calls


def test_list_drafts_skips_a_draft_that_cannot_be_fetched():
    def uid(command, *args):
        if command == "SEARCH":
            return "OK", [b"1 2"]
        return ("NO", [None]) if args[0] == "1" else _summary_reply(2, b"")

    conn = _FakeConn(list=DRAFTS_LIST, select=("OK", [b"2"]), uid=uid)

    drafts = imap_client.list_drafts(_imap(conn))

    assert [d.uid for d in drafts] == ["2"]


@pytest.mark.parametrize("search_reply", [("OK", [b""]), ("NO", [b"denied"])])
def test_list_drafts_returns_an_empty_list_when_the_search_finds_nothing(search_reply):
    conn = _FakeConn(list=DRAFTS_LIST, select=("OK", [b"0"]), uid=search_reply)

    drafts = imap_client.list_drafts(_imap(conn))

    assert drafts == []


def test_list_drafts_raises_when_the_drafts_folder_cannot_be_selected():
    conn = _FakeConn(list=DRAFTS_LIST, select=("NO", [b"denied"]))

    with pytest.raises(imap_client.FolderNotFoundError, match="Could not select Drafts"):
        imap_client.list_drafts(_imap(conn))


def _saved_draft(conn: _FakeConn) -> EmailMessage:
    *_, raw = next(call for call in conn.calls if call[0] == "append")
    return cast(EmailMessage, email.message_from_bytes(raw, policy=email.policy.default))


def test_create_draft_appends_a_flagged_message_to_the_drafts_folder():
    conn = _FakeConn(list=DRAFTS_LIST, append=("OK", [b"done"]))

    result = imap_client.create_draft(
        _imap(conn),
        "me@naver.com",
        "Hong, Gildong",
        ["a@example.com", "b@example.com"],
        "회의 안내",
        "본문",
        cc=["c@example.com"],
    )

    saved = _saved_draft(conn)
    assert result == {"success": True, "message": "Draft saved successfully."}
    assert conn.calls[-1][:4] == ("append", '"Drafts"', "\\Draft", None)
    assert str(saved["From"]) == '"Hong, Gildong" <me@naver.com>'
    assert str(saved["To"]) == "a@example.com, b@example.com"
    assert str(saved["Cc"]) == "c@example.com"
    assert str(saved["Subject"]) == "회의 안내"
    assert saved.get_content_type() == "text/plain"
    assert saved.get_content().strip() == "본문"


def test_create_draft_saves_an_html_body_when_asked():
    conn = _FakeConn(list=DRAFTS_LIST, append=("OK", [b"done"]))

    imap_client.create_draft(
        _imap(conn), "me@naver.com", "", ["a@example.com"], "s", "<p>hi</p>", "text/html"
    )

    saved = _saved_draft(conn)
    assert saved.get_content_type() == "text/html"
    assert saved.get_content().strip() == "<p>hi</p>"


def test_create_draft_uses_the_bare_address_without_a_full_name():
    conn = _FakeConn(list=DRAFTS_LIST, append=("OK", [b"done"]))

    imap_client.create_draft(_imap(conn), "me@naver.com", "", ["a@example.com"], "s", "b")

    saved = _saved_draft(conn)
    assert str(saved["From"]) == "me@naver.com"
    assert saved["Cc"] is None


def test_create_draft_rejects_a_line_break_in_the_display_name():
    conn = _FakeConn(list=DRAFTS_LIST, append=("OK", [b"done"]))

    with pytest.raises(ValueError, match="CRLF"):
        imap_client.create_draft(
            _imap(conn), "me@naver.com", "Kim\r\nBcc: x@example.com", ["a@example.com"], "s", "b"
        )

    assert not any(call[0] == "append" for call in conn.calls)


def test_create_draft_rejects_an_unknown_body_type_before_touching_the_server():
    conn = _FakeConn()

    with pytest.raises(ValueError, match="body_type must be one of"):
        imap_client.create_draft(
            _imap(conn), "me@naver.com", "", ["a@example.com"], "s", "b", "text/xml"
        )

    assert conn.calls == []


def test_create_draft_raises_when_the_server_refuses_to_save():
    conn = _FakeConn(list=DRAFTS_LIST, append=("NO", [b"quota exceeded"]))

    with pytest.raises(imap_client.MailIMAPError, match="Failed to save draft"):
        imap_client.create_draft(_imap(conn), "me@naver.com", "", ["a@example.com"], "s", "b")


# ---- reading mail and attachments ----


def _mixed_mail(attachment_headers: bytes, attachment_body: bytes = b"aGk=") -> bytes:
    return (
        b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n'
        b"--b\r\nContent-Type: text/plain\r\n\r\nsee attached\r\n"
        b"--b\r\n" + attachment_headers + b"\r\n\r\n" + attachment_body + b"\r\n--b--\r\n"
    )


UNNAMED_ATTACHMENT = (
    b"Content-Type: application/octet-stream\r\n"
    b"Content-Disposition: attachment\r\n"
    b"Content-Transfer-Encoding: base64"
)


def test_read_email_rejects_a_missing_folder():
    conn = _FakeConn(select=("NO", [b"no such folder"]))

    with pytest.raises(imap_client.FolderNotFoundError, match="Folder 'Gone' not found"):
        imap_client.read_email(_imap(conn), "5", "Gone")


def test_read_email_names_an_unnamed_attachment_by_its_part_number():
    conn = _OneMessage(_mixed_mail(UNNAMED_ATTACHMENT))

    mail = imap_client.read_email(_imap(conn), "5")

    assert [(a.filename, a.size, a.part_number) for a in mail.attachments] == [
        ("attachment_3", 2, "3")
    ]


def test_read_email_returns_the_html_body_when_there_is_no_text_part():
    raw = b"Content-Type: text/html; charset=utf-8\r\n\r\n<p>hi</p>\r\n"

    mail = imap_client.read_email(_imap(_OneMessage(raw)), "5")

    assert mail.body_html.strip() == "<p>hi</p>"
    assert mail.body_text == ""


def test_download_attachment_names_an_unnamed_part_by_its_number():
    conn = _OneMessage(_mixed_mail(UNNAMED_ATTACHMENT))

    result = imap_client.download_attachment(_imap(conn), "5", "3")

    assert to_dict(result) == {
        "filename": "attachment_3",
        "content_type": "application/octet-stream",
        "size": 2,
        "content_base64": "aGk=",
    }


def test_download_attachment_decodes_an_encoded_filename():
    encoded = base64.b64encode("영수증.pdf".encode()).decode()
    headers = (
        b"Content-Type: application/pdf\r\n"
        b'Content-Disposition: attachment; filename="=?UTF-8?B?' + encoded.encode() + b'?="\r\n'
        b"Content-Transfer-Encoding: base64"
    )
    conn = _OneMessage(_mixed_mail(headers))

    result = imap_client.download_attachment(_imap(conn), "5", "3")

    assert result.filename == "영수증.pdf"


def test_download_attachment_rejects_a_missing_folder():
    conn = _FakeConn(select=("NO", [b"no such folder"]))

    with pytest.raises(imap_client.FolderNotFoundError, match="Folder 'Gone' not found"):
        imap_client.download_attachment(_imap(conn), "5", "2", "Gone")


def test_download_attachment_rejects_a_part_without_content():
    conn = _OneMessage(_mixed_mail(UNNAMED_ATTACHMENT))

    with pytest.raises(imap_client.MailIMAPError, match="has no content"):
        imap_client.download_attachment(_imap(conn), "5", "1")


def test_download_attachment_rejects_an_unknown_part_number():
    conn = _OneMessage(_mixed_mail(UNNAMED_ATTACHMENT))

    with pytest.raises(imap_client.MailIMAPError, match="part '9' not found"):
        imap_client.download_attachment(_imap(conn), "5", "9")


def test_download_attachment_rejects_a_file_over_the_size_limit(monkeypatch):
    monkeypatch.setattr(imap_client, "MAX_ATTACHMENT_BYTES", 1)
    conn = _OneMessage(_mixed_mail(UNNAMED_ATTACHMENT))

    with pytest.raises(imap_client.MailIMAPError, match="exceeds"):
        imap_client.download_attachment(_imap(conn), "5", "3")


def test_download_attachment_accepts_a_file_exactly_at_the_size_limit(monkeypatch):
    monkeypatch.setattr(imap_client, "MAX_ATTACHMENT_BYTES", 2)
    conn = _OneMessage(_mixed_mail(UNNAMED_ATTACHMENT))

    result = imap_client.download_attachment(_imap(conn), "5", "3")

    assert result.size == 2


def test_read_thread_rejects_a_missing_folder():
    conn = _FakeConn(select=("NO", [b"no such folder"]))

    with pytest.raises(imap_client.FolderNotFoundError, match="Folder 'Gone' not found"):
        imap_client.read_thread(_imap(conn), "<a@example.com>", "Gone")


def test_read_thread_collects_referenced_messages_oldest_first_and_skips_missing_ones():
    messages = {
        "7": b"Message-ID: <a@example.com>\r\nDate: Tue, 10 Nov 2026 09:00:00 +0900\r\n\r\nA\r\n",
        "3": b"Message-ID: <b@example.com>\r\nDate: Thu, 12 Nov 2026 09:00:00 +0900\r\n\r\nB\r\n",
    }
    hits = {
        ("Message-ID", '"<b@example.com>"'): b"3",
        ("Message-ID", '"<a@example.com>"'): b"7",
        ("In-Reply-To", '"<a@example.com>"'): b"3 9",
    }
    reply_headers = b"In-Reply-To: <a@example.com>\r\nReferences: <a@example.com>\r\n\r\n"

    def uid(command, *args):
        if command == "SEARCH":
            terms = [arg for arg in args if arg != "OR"]
            pairs = [(terms[i + 1], terms[i + 2]) for i in range(0, len(terms), 3)]
            return "OK", [b" ".join(hits[pair] for pair in pairs if pair in hits)]
        target = args[0].decode() if isinstance(args[0], bytes) else args[0]
        if "REFERENCES" in args[1]:
            meta = b"3 (BODY[HEADER.FIELDS (REFERENCES IN-REPLY-TO)] {%d}" % len(reply_headers)
            return "OK", [(meta, reply_headers), b")"]
        if target not in messages:
            return "OK", [None]
        meta = b"1 (UID %s FLAGS () BODY[] {%d}" % (target.encode(), len(messages[target]))
        return "OK", [(meta, messages[target]), b")"]

    conn = _FakeConn(select=("OK", [b"2"]), uid=uid)

    thread = imap_client.read_thread(_imap(conn), "<b@example.com>")

    assert [mail.uid for mail in thread] == ["7", "3"]


# ---- mailbox organization ----


@pytest.mark.parametrize(
    ("data", "reason"),
    [([b"Mailbox exists"], "Mailbox exists"), ([], ""), (["plain text"], "plain text")],
)
def test_server_reason_reads_the_first_reply_line(data, reason):
    result = imap_client._server_reason(data)

    assert result == reason


def test_create_folder_raises_with_the_server_reason():
    conn = _FakeConn(create=("NO", [b"Mailbox exists"]))

    with pytest.raises(
        imap_client.MailIMAPError, match="Failed to create folder '영수증': Mailbox exists"
    ):
        imap_client.create_folder(_imap(conn), "영수증")


def test_move_emails_rejects_a_missing_source_folder_without_moving_anything():
    conn = _FakeConn(select=("NO", [b"no such folder"]))

    with pytest.raises(imap_client.FolderNotFoundError, match="Folder 'Gone' not found"):
        imap_client.move_emails(_imap(conn), ["3"], "영수증", folder="Gone")

    assert not any(call[0] == "uid" for call in conn.calls)


def test_move_emails_points_to_create_folder_when_the_server_refuses():
    conn = _FakeConn(select=("OK", [b"1"]), uid=("NO", [b"[TRYCREATE] no such mailbox"]))

    with pytest.raises(imap_client.MailIMAPError, match=r"TRYCREATE.*create_folder"):
        imap_client.move_emails(_imap(conn), ["3"], "영수증")


def test_mark_read_sets_the_seen_flag_by_default():
    conn = _FakeConn(select=("OK", [b"1"]), uid=("OK", [b"done"]))

    result = imap_client.mark_read(_imap(conn), ["4"])

    assert conn.calls[-1] == ("uid", "STORE", "4", "+FLAGS.SILENT", "(\\Seen)")
    assert result == {"success": True, "message": "Server accepted marking 1 UID(s) as read."}


def test_mark_read_raises_with_the_server_reason():
    conn = _FakeConn(select=("OK", [b"1"]), uid=("NO", [b"read-only mailbox"]))

    with pytest.raises(imap_client.MailIMAPError, match="read-only mailbox"):
        imap_client.mark_read(_imap(conn), ["4"])


def test_trash_emails_raises_when_the_account_has_no_trash_folder():
    conn = _FakeConn(list=("OK", [b'(\\HasNoChildren) "/" "INBOX"']))

    with pytest.raises(imap_client.FolderNotFoundError, match=r"role '\\Trash'"):
        imap_client.trash_emails(_imap(conn), ["8"])

    assert not any(call[0] == "uid" for call in conn.calls)


# ---- sending mail ----


@pytest.fixture
def smtp(monkeypatch):
    """Replace smtplib.SMTP_SSL with a fake that records the connection, login and messages."""
    state = SimpleNamespace(connected=[], logins=[], sent=[], error=None)

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            state.connected.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, user, password):
            state.logins.append((user, password))
            if state.error:
                raise state.error

        def send_message(self, msg):
            state.sent.append(msg)

    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", FakeSMTP)
    return state


def test_send_email_logs_in_to_the_provider_host_and_reports_the_recipients(smtp):
    result = smtp_client.send_email(
        "me@daum.net", "pw", "", ["a@example.com", "b@example.com"], "s", "b"
    )

    assert smtp.connected == [("smtp.daum.net", 465, 30)]
    assert smtp.logins == [("me@daum.net", "pw")]
    assert len(smtp.sent) == 1
    assert result == {"success": True, "message": "Email sent to a@example.com, b@example.com"}


def test_send_email_sets_cc_and_reply_headers(smtp):
    smtp_client.send_email(
        "me@naver.com",
        "pw",
        "",
        ["a@example.com"],
        "Re: 회의",
        "b",
        cc=["c@example.com"],
        in_reply_to="<b@example.com>",
        references=["<a@example.com>", "<b@example.com>"],
    )

    sent = smtp.sent[0]
    assert str(sent["Cc"]) == "c@example.com"
    assert str(sent["In-Reply-To"]) == "<b@example.com>"
    assert str(sent["References"]) == "<a@example.com> <b@example.com>"


def test_send_email_dates_the_message_itself(smtp):
    smtp_client.send_email("me@kakao.com", "pw", "", ["a@example.com"], "s", "b")

    sent_at = email.utils.parsedate_to_datetime(str(smtp.sent[0]["Date"]))
    assert abs(sent_at.timestamp() - time.time()) < 60


def test_send_email_sends_an_html_body_when_asked(smtp):
    smtp_client.send_email(
        "me@naver.com", "pw", "", ["a@example.com"], "s", "<p>hi</p>", "text/html"
    )

    assert smtp.sent[0].get_content_type() == "text/html"


def test_send_email_rejects_an_unknown_body_type_before_connecting(smtp):
    with pytest.raises(ValueError, match="body_type must be one of"):
        smtp_client.send_email("me@naver.com", "pw", "", ["a@example.com"], "s", "b", "text/xml")

    assert smtp.connected == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject": "s\r\nBcc: x@example.com"},
        {"full_name": "Kim\nBcc: x@example.com"},
        {"in_reply_to": "<a@example.com>\r\nBcc: x@example.com"},
        {"references": ["<a@example.com>", "<b@example.com>\nBcc: x@example.com"]},
    ],
)
def test_send_email_rejects_a_line_break_in_any_header_value(smtp, overrides):
    arguments = {"full_name": "", "subject": "s", **overrides}

    with pytest.raises(ValueError, match="CRLF"):
        smtp_client.send_email(
            "me@naver.com",
            "pw",
            arguments.pop("full_name"),
            ["a@example.com"],
            body="b",
            **arguments,
        )

    assert smtp.connected == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), "SMTP authentication failed"),
        (smtplib.SMTPRecipientsRefused({}), "Failed to send email"),
        (OSError("network is down"), r"Cannot connect to SMTP server \(smtp\.naver\.com:465\)"),
    ],
)
def test_send_email_turns_transport_errors_into_a_mail_error(smtp, error, message):
    smtp.error = error

    with pytest.raises(smtp_client.MailSMTPError, match=message) as raised:
        smtp_client.send_email("me@naver.com", "pw", "", ["a@example.com"], "s", "b")

    assert raised.value.__cause__ is error
    assert smtp.sent == []


# ---- server start-up ----


@pytest.fixture
def stdio_runs(monkeypatch):
    """Start with no MAIL_* variables, and record the transports the server is started with."""
    for key in [key for key in os.environ if key.startswith("MAIL_")]:
        monkeypatch.delenv(key)
    runs = []

    def run(transport):
        runs.append(transport)

    monkeypatch.setattr(server.mcp, "run", run)
    return runs


def test_main_runs_the_stdio_server_when_the_accounts_are_valid(monkeypatch, stdio_runs):
    monkeypatch.setenv("MAIL_ADDRESS", "me@naver.com")
    monkeypatch.setenv("MAIL_PASSWORD", "dummy")

    server.main()

    assert stdio_runs == ["stdio"]


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({}, "MAIL_ADDRESS"),
        (
            {"MAIL_ADDRESS": "me@example.com", "MAIL_PASSWORD": "dummy"},
            "Unsupported mail domain 'example.com'",
        ),
        (
            {
                "MAIL_ACCOUNTS": "home,work",
                "MAIL_HOME_ADDRESS": "me@naver.com",
                "MAIL_HOME_PASSWORD": "dummy",
                "MAIL_WORK_ADDRESS": "me@example.com",
                "MAIL_WORK_PASSWORD": "dummy",
            },
            "Account 'work': Unsupported mail domain 'example.com'",
        ),
    ],
)
def test_main_exits_with_the_reason_when_the_configuration_is_unusable(
    monkeypatch, stdio_runs, env, message
):
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(SystemExit) as exit_info:
        server.main()

    assert message in str(exit_info.value.code)
    assert stdio_runs == []
