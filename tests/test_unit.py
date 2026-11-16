"""Unit tests that need no mail account or network."""

from __future__ import annotations

import base64
import contextlib
import email
import imaplib
import json
import os
import socket
import subprocess
import sys
import threading
import unicodedata
from typing import cast

import pytest

from korean_mail_mcp import imap_client, smtp_client
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
