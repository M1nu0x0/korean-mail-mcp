"""IMAP client for Naver, Daum and Kakao mail."""

from __future__ import annotations

import base64
import contextlib
import email
import email.errors
import email.header
import email.headerregistry
import email.message
import email.policy
import email.utils
import imaplib
import itertools
import re
import unicodedata
from collections.abc import Generator

from .models import (
    AttachmentContent,
    AttachmentMeta,
    Email,
    EmailSummary,
    Folder,
    Profile,
    SearchResult,
)
from .providers import SERVER_TEXT_SEARCH_HOSTS, hosts_for

IMAP_PORT = 993
TIMEOUT = 30
MAX_PAGE_SIZE = 100
MAX_UIDS_PER_CALL = 500
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_THREAD_IDS = 50  # each ID costs three SEARCH commands
ALLOWED_BODY_TYPES = {"text/plain", "text/html"}


# --- Exceptions ---


class MailIMAPError(Exception):
    """Base exception for IMAP operations."""


class AuthenticationError(MailIMAPError):
    """IMAP login failed."""


class MailConnectionError(MailIMAPError):
    """Cannot connect to the IMAP server."""


class FolderNotFoundError(MailIMAPError):
    """Requested folder does not exist."""


class EmailNotFoundError(MailIMAPError):
    """Email with specified UID not found."""


# --- Input Sanitization ---


def _sanitize_folder_name(folder: str) -> str:
    """Ensure folder name cannot break IMAP quoted-string syntax."""
    if not folder or any(c in folder for c in '"\\\r\n\x00'):
        raise ValueError("Invalid folder name: contains prohibited characters.")
    return folder


def _mailbox(folder: str) -> str:
    """Quote a folder for an IMAP command.

    Valid Modified UTF-7, such as a raw_name from list_folders, is sent as given.
    Anything else (Korean, or ASCII like "R&D") is a display name and is encoded.
    """
    folder = _sanitize_folder_name(folder)
    is_raw = folder.isascii() and encode_mutf7(decode_mutf7(folder)) == folder
    return f'"{folder if is_raw else encode_mutf7(folder)}"'


def _uid_set(uids: list[str]) -> str:
    if not uids:
        raise ValueError("uids must not be empty.")
    if len(uids) > MAX_UIDS_PER_CALL:
        raise ValueError(f"At most {MAX_UIDS_PER_CALL} UIDs per call, got {len(uids)}.")
    return ",".join(_sanitize_uid(uid) for uid in uids)


def _sanitize_message_id(value: str) -> str:
    """Reject Message-IDs containing characters that could break IMAP search."""
    if not value or '"' in value or not (value.isascii() and value.isprintable()):
        raise ValueError("Invalid Message-ID: contains prohibited characters.")
    return value


def _sanitize_uid(uid: str) -> str:
    """Ensure UID contains only digits."""
    if not uid or not re.fullmatch(r"[0-9]+", uid.strip()):
        raise ValueError(f"Invalid UID: must be a positive integer, got '{uid}'.")
    return uid.strip()


def _sanitize_header_value(value: str) -> str:
    """Strip CRLF to prevent header injection."""
    if "\r" in value or "\n" in value:
        raise ValueError("Header value contains prohibited CRLF characters.")
    return value


def _validate_body_type(body_type: str) -> str:
    """Validate body_type against allowed values."""
    if body_type not in ALLOWED_BODY_TYPES:
        raise ValueError(f"body_type must be one of {ALLOWED_BODY_TYPES}, got '{body_type}'.")
    return body_type


def _validate_pagination(page: int, page_size: int) -> tuple[int, int]:
    """Validate pagination parameters."""
    if page < 1:
        raise ValueError("page must be >= 1.")
    if not (1 <= page_size <= MAX_PAGE_SIZE):
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}.")
    return page, page_size


# --- Connection ---


@contextlib.contextmanager
def imap_connection(email_address: str, password: str) -> Generator[imaplib.IMAP4_SSL, None, None]:
    """Create an authenticated IMAP connection.

    The connection is automatically closed on exit.
    Login errors are caught separately from operation errors.
    """
    host, _ = hosts_for(email_address)
    try:
        conn = imaplib.IMAP4_SSL(host, IMAP_PORT, timeout=TIMEOUT)
    except (OSError, imaplib.IMAP4.error) as e:
        raise MailConnectionError(
            f"Cannot connect to IMAP server ({host}:{IMAP_PORT}). "
            f"Check your network connection. Error: {e}"
        ) from e

    try:
        conn.login(email_address, password)
    except imaplib.IMAP4.error as e:
        with contextlib.suppress(Exception):
            conn.logout()
        raise AuthenticationError(
            "IMAP authentication failed. Check your email address and app password."
        ) from e

    try:
        yield conn
    finally:
        with contextlib.suppress(Exception):
            conn.logout()


# --- Encoding Utilities ---


def decode_header_value(raw: str | None) -> str:
    """Decode RFC 2047 encoded header value, handling Korean charsets."""
    if not raw:
        return ""
    try:
        decoded_parts = email.header.decode_header(raw)
    except email.errors.HeaderParseError:
        # A base64 word with one character past a multiple of four makes decode_header raise,
        # which would fail the whole call. The policy parser keeps such a word as text.
        return str(email.policy.default.header_fetch_parse("Subject", raw))
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            decoded = _decode_bytes(part, charset)
        else:
            decoded = part
        result.append(decoded)
    return "".join(result)


def _decode_bytes(data: bytes, charset: str | None = None) -> str:
    """Decode bytes with charset fallback chain: given → UTF-8 → EUC-KR → CP949 → latin-1."""
    charsets = []
    if charset:
        charsets.append(charset)
    charsets.extend(["utf-8", "euc-kr", "cp949", "latin-1"])

    for cs in charsets:
        try:
            return data.decode(cs)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1", errors="replace")


def decode_body(payload: bytes, charset: str | None) -> str:
    """Decode email body with charset fallback chain."""
    return _decode_bytes(payload, charset)


def encode_mutf7(text: str) -> str:
    """Encode a Unicode string to Modified UTF-7 for IMAP folder names."""
    result = []
    buf = ""
    for ch in text:
        if 0x20 <= ord(ch) <= 0x7E:
            if buf:
                encoded = buf.encode("utf-16-be")
                b64 = base64.b64encode(encoded).decode("ascii").rstrip("=")
                result.append("&" + b64.replace("/", ",") + "-")
                buf = ""
            if ch == "&":
                result.append("&-")
            else:
                result.append(ch)
        else:
            buf += ch
    if buf:
        encoded = buf.encode("utf-16-be")
        b64 = base64.b64encode(encoded).decode("ascii").rstrip("=")
        result.append("&" + b64.replace("/", ",") + "-")
    return "".join(result)


def decode_mutf7(data: str) -> str:
    """Decode Modified UTF-7 folder name to Unicode; malformed input comes back unchanged."""
    try:
        return _decode_mutf7(data)
    except ValueError:
        return data


def _decode_mutf7(data: str) -> str:
    result = []
    i = 0
    while i < len(data):
        if data[i] == "&":
            j = data.index("-", i + 1)
            if j == i + 1:
                result.append("&")
            else:
                b64_str = data[i + 1 : j].replace(",", "/")
                padding = 4 - (len(b64_str) % 4)
                if padding != 4:
                    b64_str += "=" * padding
                decoded = base64.b64decode(b64_str, validate=True).decode("utf-16-be")
                result.append(decoded)
            i = j + 1
        else:
            result.append(data[i])
            i += 1
    return "".join(result)


def _parse_date(date_str: str | None) -> str:
    """Parse email date to ISO 8601 string."""
    if not date_str:
        return ""
    try:
        return email.utils.parsedate_to_datetime(date_str).isoformat()
    except (TypeError, ValueError):
        return ""


def _parse_address(addr: str | None) -> str:
    """Parse and decode email address with display name."""
    if not addr:
        return ""
    return decode_header_value(addr)


def _parse_address_list(header: str | None) -> list[str]:
    """Parse an address list header; commas inside quoted display names stay in the name."""
    if not header:
        return []
    return [
        f"{decode_header_value(name)} <{addr}>" if name else addr
        for name, addr in email.utils.getaddresses([header])
        if addr
    ]


# --- IMAP Operations ---
# All functions accept an authenticated IMAP connection as first parameter.


def get_profile(conn: imaplib.IMAP4_SSL, email_address: str, full_name: str) -> Profile:
    """Get account profile with mailbox statistics."""
    status, data = conn.select("INBOX", readonly=True)
    if status != "OK":
        raise MailIMAPError("Failed to select INBOX.")

    total = int(data[0] or 0)

    status, data = conn.search(None, "UNSEEN")
    if status != "OK":
        raise MailIMAPError("Failed to search for unseen messages.")

    unseen_uids = data[0].split()
    unseen = len(unseen_uids)

    return Profile(
        email=email_address,
        full_name=full_name,
        total_messages=total,
        unseen_messages=unseen,
    )


_LIST_ITEM_RE = re.compile(r'\((?P<flags>.*?)\)\s+"(?P<sep>.+?)"\s+"?(?P<name>.+?)"?$')


def _parse_list_item(item: object) -> tuple[str, str] | None:
    """Parse one IMAP LIST response line into (flags, raw folder name)."""
    if not isinstance(item, bytes):
        return None
    match = _LIST_ITEM_RE.match(item.decode("utf-8"))
    if not match:
        return None
    return match.group("flags"), match.group("name").strip().strip('"')


def list_folders(conn: imaplib.IMAP4_SSL) -> list[Folder]:
    """List all mailbox folders with message counts."""
    status, folder_data = conn.list()
    if status != "OK":
        raise MailIMAPError("Failed to list folders.")

    folders = []
    for item in folder_data:
        parsed = _parse_list_item(item)
        if not parsed:
            continue
        _, raw_name = parsed
        display_name = decode_mutf7(raw_name)

        msg_count = 0
        unseen_count = 0
        try:
            status, count_data = conn.status(f'"{raw_name}"', "(MESSAGES UNSEEN)")
            if status == "OK" and count_data[0]:
                count_str = (
                    count_data[0].decode("utf-8")
                    if isinstance(count_data[0], bytes)
                    else count_data[0]
                )
                msg_match = re.search(r"MESSAGES\s+(\d+)", count_str)
                unseen_match = re.search(r"UNSEEN\s+(\d+)", count_str)
                if msg_match:
                    msg_count = int(msg_match.group(1))
                if unseen_match:
                    unseen_count = int(unseen_match.group(1))
        except imaplib.IMAP4.error:
            pass

        folders.append(
            Folder(
                name=display_name,
                raw_name=raw_name,
                message_count=msg_count,
                unseen_count=unseen_count,
            )
        )

    return folders


def _find_folder_by_role(conn: imaplib.IMAP4_SSL, role: str, fallback_names: list[str]) -> str:
    """Find a folder by its special-use attribute or name matching.

    Args:
        conn: Authenticated IMAP connection.
        role: Special-use attribute to look for (e.g., '\\Drafts').
        fallback_names: List of folder names to try if attribute not found.

    Returns:
        The raw IMAP folder name.
    """
    status, folder_data = conn.list()
    if status != "OK":
        raise MailIMAPError("Failed to list folders.")

    for item in folder_data:
        parsed = _parse_list_item(item)
        if parsed and role.lower() in parsed[0].lower():
            return parsed[1]

    for item in folder_data:
        parsed = _parse_list_item(item)
        if not parsed:
            continue
        _, raw_name = parsed
        display_name = decode_mutf7(raw_name)

        for name in fallback_names:
            if display_name.lower() == name.lower() or raw_name.lower() == name.lower():
                return raw_name

    raise FolderNotFoundError(
        f"Could not find folder with role '{role}'. "
        f"Tried names: {fallback_names}. Use list_folders to see available folders."
    )


def _find_drafts_folder(conn: imaplib.IMAP4_SSL) -> str:
    """Find the Drafts folder."""
    return _find_folder_by_role(conn, "\\Drafts", ["Drafts", "임시보관함", "&BCIENA0RBBQ-"])


_SEARCH_DATE_RE = re.compile(r"\d{1,2}-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{4}")


def _search_date(value: str) -> str:
    if not _SEARCH_DATE_RE.fullmatch(value):
        raise ValueError(f"Invalid date '{value}': use DD-Mon-YYYY, e.g. 01-Jan-2026.")
    return value


def _build_search_criteria(
    date_from: str | None, date_to: str | None, is_read: bool | None
) -> list[str]:
    criteria: list[str] = []
    if date_from:
        criteria += ["SINCE", _search_date(date_from)]
    if date_to:
        criteria += ["BEFORE", _search_date(date_to)]
    if is_read is not None:
        criteria.append("SEEN" if is_read else "UNSEEN")
    return criteria or ["ALL"]


def _search_string(value: str) -> bytes:
    """Encode a search value as an IMAP quoted string."""
    if any(c in value for c in "\r\n\x00"):
        raise ValueError("Search value contains prohibited characters.")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'.encode()


# Naver's SEARCH is case-sensitive on every key (SUBJECT, FROM, HEADER, with or without
# CHARSET) and has no SEARCH=FUZZY. It accepts 1,024 ORed terms at 7-10 ms a term, so every
# casing of a short text can be sent: 7 cased letters are 128 terms, about a second.
MAX_CASED_LETTERS = 7
MAX_TEXT_CHUNKS = 3
# The most ORed terms in one SEARCH that Naver was measured to accept.
MAX_SERVER_TERMS = 1024
HEADER_FETCH_BATCH = 200
# Messages a header FETCH left out are asked for again in smaller batches.
HEADER_RETRY_BATCH = 50


def _is_cased(char: str) -> bool:
    return char.lower() != char.upper()


def _casings(text: str) -> list[str]:
    """Every upper/lower casing of `text`."""
    options = [(c.lower(), c.upper()) if _is_cased(c) else (c,) for c in text]
    return list(dict.fromkeys("".join(choice) for choice in itertools.product(*options)))


def _casing_chunks(text: str) -> list[str]:
    """Cut `text` into consecutive pieces of at most MAX_CASED_LETTERS cased letters."""
    pieces, current, cased = [], "", 0
    for char in text:
        if _is_cased(char) and cased == MAX_CASED_LETTERS:
            pieces.append(current)
            current, cased = "", 0
        current += char
        cased += _is_cased(char)
    pieces.append(current)
    return [piece.strip() for piece in pieces if piece.strip()]


def _text_criteria(wanted: dict[str, str]) -> tuple[list[str | bytes], bool]:
    """Case-insensitive SEARCH criteria for a server that matches decoded headers.

    Returns the criteria and whether the hits still have to be checked here. A text of
    up to MAX_CASED_LETTERS cased letters is matched exactly by ORing all its casings.
    A longer one is cut into such pieces that are ANDed, which also matches messages
    holding the pieces apart from each other, so those hits are a superset.

    Every piece costs up to 2**MAX_CASED_LETTERS terms. The pieces sent per field are
    limited so that all fields together stay within MAX_SERVER_TERMS; the check here
    covers the pieces left out.
    """
    criteria: list[str | bytes] = []
    needs_check = False
    per_field = max(
        1, min(MAX_TEXT_CHUNKS, MAX_SERVER_TERMS // (len(wanted) * 2**MAX_CASED_LETTERS))
    )
    for name, text in wanted.items():
        chunks = _casing_chunks(text)
        needs_check = needs_check or len(chunks) > 1
        for chunk in chunks[:per_field]:
            variants = _casings(chunk)
            criteria += ["OR"] * (len(variants) - 1)
            for variant in variants:
                criteria += [name.upper(), _search_string(variant)]
    return criteria, needs_check


MIN_ENCODED_FRAGMENT = 4
TEXT_SEARCH_MODES = ("auto", "server", "local")


def _base64_fragments(data: bytes) -> list[bytes]:
    """The base64 text `data` turns into at each of the three byte alignments.

    Characters that also depend on the neighbouring bytes are trimmed off, so every
    fragment appears verbatim wherever `data` was base64-encoded at that alignment.
    """
    fragments = []
    for lead in range(3):
        tail = -(lead + len(data)) % 3
        encoded = base64.b64encode(b"\0" * lead + data + b"\0" * tail)
        fragments.append(encoded[-(-lead * 8 // 6) : len(encoded) - -(-tail * 8 // 6)])
    return fragments


def _quoted_printable(data: bytes) -> bytes:
    """`data` as it appears inside a Q-encoded word: space is _, other non-alphanumerics =XX."""
    return b"".join(
        b"_"
        if byte == 0x20
        else bytes([byte])
        if chr(byte).isalnum() and byte < 128
        else b"=%02X" % byte
        for byte in data
    )


def _encoded_forms(text: str) -> list[bytes]:
    """Byte strings to look for in raw headers that would decode to `text`."""
    if text.isascii():
        return [text.encode("ascii")]
    forms: list[bytes] = []
    for charset in ("utf-8", "cp949"):
        try:
            data = text.encode(charset)
        except UnicodeEncodeError:
            continue
        quoted = _quoted_printable(data)
        # a space inside a Q-encoded word is written either as _ or as =20
        forms += [*_base64_fragments(data), quoted, quoted.replace(b"_", b"=20")]
    # shorter fragments match unrelated base64; the Q-encoded form of any character is longer
    return [form for form in dict.fromkeys(forms) if len(form) >= MIN_ENCODED_FRAGMENT]


def _raw_text_criteria(wanted: dict[str, str]) -> list[str | bytes]:
    """SEARCH criteria for servers that match the undecoded header bytes (Daum, Kakao).

    A Korean word is stored as base64 or quoted-printable in UTF-8 or EUC-KR, so each
    of those forms is searched for. This is approximate: a word that straddles two
    encoded-words is missed (95 of 98 real matches were found on a Daum mailbox).
    """
    criteria: list[str | bytes] = []
    for name, text in wanted.items():
        forms = _encoded_forms(text)
        criteria += ["OR"] * (len(forms) - 1)
        for form in forms:
            criteria += [name.upper(), _search_string(form.decode("ascii"))]
    return criteria


def _searchable(text: str) -> str:
    """Reduce text to a form in which equal-looking strings compare equal.

    NFKC composes decomposed Hangul (text typed or named on macOS arrives as jamo) and
    turns full-width letters into ASCII; whitespace runs, including the line break of a
    folded header, become one space.
    """
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _headers_match(headers: email.message.Message, wanted: dict[str, str]) -> bool:
    """True when every wanted header contains its text."""
    return all(
        _searchable(text) in _searchable(decode_header_value(headers.get(name)))
        for name, text in wanted.items()
    )


def _fetch_header_matches(
    conn: imaplib.IMAP4_SSL, uid_set: str, candidates: set[bytes], wanted: dict[str, str]
) -> tuple[set[bytes], set[bytes]]:
    """FETCH the headers of `uid_set`; return the candidate UIDs answered and those that match."""
    status, data = conn.uid("FETCH", uid_set, "(UID BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT)])")
    if status != "OK":
        raise MailIMAPError("Failed to fetch headers for search.")
    seen: set[bytes] = set()
    matched: set[bytes] = set()
    for part in data:
        if not isinstance(part, tuple):
            continue
        uid_match = re.search(rb"UID (\d+)", part[0])
        if not uid_match or uid_match.group(1) not in candidates:
            continue
        seen.add(uid_match.group(1))
        if _headers_match(email.message_from_bytes(part[1]), wanted):
            matched.add(uid_match.group(1))
    return seen, matched


def _filter_by_headers(
    conn: imaplib.IMAP4_SSL, uids: list[bytes], wanted: dict[str, str], sparse: bool = False
) -> list[bytes]:
    """Keep the UIDs whose From/To/Subject contain the wanted text.

    Matching happens here, on decoded headers, because Daum and Kakao return no
    hits for a non-ASCII SEARCH (verified against a mailbox with 98 real matches).

    `uids` normally is every message the server kept, so one first:last range covers
    it. With `sparse`, only the listed UIDs are fetched: on Naver each fetched header
    costs about 50 ms, and a range would pull in the messages between the hits.

    A server can answer a large FETCH with OK and leave messages out, which would hide
    real matches, so the UIDs that got no answer are asked for once more in small
    batches. One still missing after that was most likely deleted since the search.
    """
    if not uids:
        return []
    candidates = set(uids)
    numbers = [uid.decode("ascii") for uid in uids]
    if sparse:
        batches = [
            ",".join(numbers[i : i + HEADER_FETCH_BATCH])
            for i in range(0, len(numbers), HEADER_FETCH_BATCH)
        ]
    else:
        batches = [f"{numbers[0]}:{numbers[-1]}"]

    seen: set[bytes] = set()
    matched: set[bytes] = set()
    for batch in batches:
        batch_seen, batch_matched = _fetch_header_matches(conn, batch, candidates, wanted)
        seen |= batch_seen
        matched |= batch_matched

    missing = [number for number, uid in zip(numbers, uids, strict=True) if uid not in seen]
    for i in range(0, len(missing), HEADER_RETRY_BATCH):
        _, retry_matched = _fetch_header_matches(
            conn, ",".join(missing[i : i + HEADER_RETRY_BATCH]), candidates, wanted
        )
        matched |= retry_matched
    return [uid for uid in uids if uid in matched]


def search_emails(
    conn: imaplib.IMAP4_SSL,
    folder: str = "INBOX",
    sender: str | None = None,
    recipient: str | None = None,
    subject: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    is_read: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    text_search: str = "auto",
) -> SearchResult:
    """Search emails with filters and pagination.

    text_search picks where sender/recipient/subject are matched: "local" fetches the
    headers and compares decoded text (exact everywhere, slow on Naver), "server" asks
    the server (exact but case-sensitive and capped at 1,000 on Naver, approximate on
    Daum and Kakao), "auto" takes server on Naver and local elsewhere.
    """
    if text_search not in TEXT_SEARCH_MODES:
        raise ValueError(f"text_search must be one of {TEXT_SEARCH_MODES}, got '{text_search}'.")
    folder = _sanitize_folder_name(folder)
    page, page_size = _validate_pagination(page, page_size)
    status, _ = conn.select(_mailbox(folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError(
            f"Folder '{folder}' not found. Use list_folders to see available folders."
        )

    wanted = {"From": sender, "To": recipient, "Subject": subject}
    # the server only finds composed Hangul; a blank filter would match everything
    wanted = {
        name: unicodedata.normalize("NFC", text.strip())
        for name, text in wanted.items()
        if text and text.strip()
    }
    decodes_headers = conn.host in SERVER_TEXT_SEARCH_HOSTS
    server_side = text_search == "server" or (text_search == "auto" and decodes_headers)

    criteria: list[str | bytes] = list(_build_search_criteria(date_from, date_to, is_read))
    check_hits = False
    if wanted and server_side:
        if decodes_headers:
            # CHARSET has to be the first search argument
            charset = [] if all(t.isascii() for t in wanted.values()) else ["CHARSET", "UTF-8"]
            text_criteria, check_hits = _text_criteria(wanted)
        else:
            charset = []
            text_criteria = _raw_text_criteria(wanted)
        criteria = charset + [c for c in criteria if c != "ALL"] + text_criteria
    # imaplib sends bytes arguments as they are; typeshed only declares str
    status, data = conn.uid("SEARCH", *criteria)  # pyright: ignore[reportArgumentType]
    if status != "OK":
        raise MailIMAPError("Search failed.")

    uid_list = data[0].split() if data[0] else []
    if wanted and (check_hits or not server_side):
        uid_list = _filter_by_headers(conn, uid_list, wanted, sparse=server_side)
    uid_list.reverse()

    total_count = len(uid_list)
    start = (page - 1) * page_size
    end = start + page_size
    page_uids = uid_list[start:end]

    emails = []
    for uid in page_uids:
        summary = _fetch_email_summary(conn, uid)
        if summary:
            emails.append(summary)

    return SearchResult(
        emails=emails,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_more=end < total_count,
    )


def _fetch_email_summary(conn: imaplib.IMAP4_SSL, uid: bytes) -> EmailSummary | None:
    """Fetch summary data for a single email by UID."""
    uid_str = uid.decode("ascii")
    status, data = conn.uid(
        "FETCH", uid_str, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
    )
    if status != "OK" or not data or data[0] is None:
        return None

    flags_str = ""
    header_data = b""
    for part in data:
        if isinstance(part, tuple):
            meta = (
                part[0].decode("utf-8", errors="replace") if isinstance(part[0], bytes) else part[0]
            )
            if "FLAGS" in meta:
                flags_match = re.search(r"FLAGS \(([^)]*)\)", meta)
                if flags_match:
                    flags_str = flags_match.group(1)
            header_data = part[1] if isinstance(part[1], bytes) else part[1].encode()

    msg = email.message_from_bytes(header_data)
    subject = decode_header_value(msg.get("Subject"))
    from_addr = _parse_address(msg.get("From"))
    date_str = _parse_date(msg.get("Date"))
    is_read = "\\Seen" in flags_str

    return EmailSummary(
        uid=uid_str,
        subject=subject,
        from_address=from_addr,
        date=date_str,
        is_read=is_read,
    )


def _part_bytes(part: email.message.Message) -> bytes | None:
    """Return the decoded content of a MIME part, or None when it has none.

    An attached .eml (message/rfc822) is parsed into a nested message, so
    get_payload(decode=True) returns None for it. Serialize the inner message
    back to bytes so it has a size and can be downloaded like any other file.
    """
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload
    inner = part.get_payload()
    if isinstance(inner, list) and len(inner) == 1 and isinstance(inner[0], email.message.Message):
        return inner[0].as_bytes()
    return None


def read_email(conn: imaplib.IMAP4_SSL, uid: str, folder: str = "INBOX") -> Email:
    """Read a full email by UID."""
    uid = _sanitize_uid(uid)
    folder = _sanitize_folder_name(folder)
    status, _ = conn.select(_mailbox(folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError(
            f"Folder '{folder}' not found. Use list_folders to see available folders."
        )

    # Daum and Kakao answer OK with no data to RFC822; BODY.PEEK[] works on all three
    status, data = conn.uid("FETCH", uid, "(FLAGS BODY.PEEK[])")
    if status != "OK" or not data or data[0] is None:
        raise EmailNotFoundError(f"Email with UID '{uid}' not found in folder '{folder}'.")

    flags_str = ""
    raw_email = b""
    for part in data:
        if isinstance(part, tuple):
            meta = (
                part[0].decode("utf-8", errors="replace") if isinstance(part[0], bytes) else part[0]
            )
            flags_match = re.search(r"FLAGS \(([^)]*)\)", meta)
            if flags_match:
                flags_str = flags_match.group(1)
            raw_email = part[1] if isinstance(part[1], bytes) else part[1].encode()

    msg = email.message_from_bytes(raw_email)

    subject = decode_header_value(msg.get("Subject"))
    from_addr = _parse_address(msg.get("From"))
    to_addrs = _parse_address_list(msg.get("To"))
    cc_addrs = _parse_address_list(msg.get("Cc"))
    date_str = _parse_date(msg.get("Date"))
    message_id = msg.get("Message-ID", "")
    in_reply_to = msg.get("In-Reply-To", "")
    refs = msg.get("References", "")
    references = refs.split() if refs else []
    flags = flags_str.split() if flags_str else []

    body_text = ""
    body_html = ""
    attachments = []

    for part_counter, part in enumerate(msg.walk(), start=1):
        content_type = part.get_content_type()
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        # inline parts with a filename (images, PDFs) are files too. A bare Content-Type name=
        # does not count: get_filename() falls back to it, and bodies sometimes carry one.
        is_file = disposition == "attachment" or (disposition == "inline" and filename)
        # message/rfc822 reports is_multipart() but is a file when attached, so test the type
        if is_file and part.get_content_maintype() != "multipart":
            if filename:
                filename = decode_header_value(filename)
            else:
                filename = f"attachment_{part_counter}"

            payload = _part_bytes(part)
            size = len(payload) if payload is not None else 0

            attachments.append(
                AttachmentMeta(
                    filename=filename,
                    content_type=content_type,
                    size=size,
                    part_number=str(part_counter),
                )
            )
        elif content_type == "text/plain" and not body_text:
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes) and payload:
                charset = part.get_content_charset()
                body_text = decode_body(payload, charset)
        elif content_type == "text/html" and not body_html:
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes) and payload:
                charset = part.get_content_charset()
                body_html = decode_body(payload, charset)

    return Email(
        uid=uid,
        message_id=message_id,
        subject=subject,
        from_address=from_addr,
        to_addresses=to_addrs,
        cc_addresses=cc_addrs,
        date=date_str,
        body_text=body_text,
        body_html=body_html,
        flags=flags,
        references=references,
        in_reply_to=in_reply_to,
        attachments=attachments,
    )


def read_thread(conn: imaplib.IMAP4_SSL, message_id: str, folder: str = "INBOX") -> list[Email]:
    """Read an email thread by Message-ID.

    Finds all related emails via References and In-Reply-To headers.
    All operations use a single connection.
    """
    message_id = _sanitize_message_id(message_id)
    folder = _sanitize_folder_name(folder)
    status, _ = conn.select(_mailbox(folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError(f"Folder '{folder}' not found.")

    target_uid = None
    status, data = conn.uid("SEARCH", "HEADER", "Message-ID", _search_string(message_id).decode())
    if status == "OK" and data[0]:
        uids = data[0].split()
        if uids:
            target_uid = uids[0]

    related_ids: list[str] = []

    if target_uid:
        status, data = conn.uid(
            "FETCH", target_uid, "(BODY.PEEK[HEADER.FIELDS (REFERENCES IN-REPLY-TO)])"
        )
        if status == "OK" and data and data[0] is not None:
            for part in data:
                if isinstance(part, tuple) and len(part) > 1:
                    header_data = part[1] if isinstance(part[1], bytes) else part[1].encode()
                    msg = email.message_from_bytes(header_data)
                    related_ids += msg.get("In-Reply-To", "").split()
                    related_ids += reversed(msg.get("References", "").split())

    # newest references first, so a header with thousands of IDs keeps the closest ones
    searchable = [mid for mid in related_ids if mid.isascii() and mid.isprintable()]
    thread_ids = list(dict.fromkeys([message_id, *searchable]))[:MAX_THREAD_IDS]
    all_uids = set()
    # Daum and Kakao scan the whole folder on every SEARCH (4-5 s for 400 mails) and an ORed
    # search costs the same as one term, so each ID gets a single search. Naver answers 0 to
    # ORed HEADER keys, but its searches are fast, so it keeps one search per header.
    headers = ("Message-ID", "References", "In-Reply-To")
    one_per_header = conn.host in SERVER_TEXT_SEARCH_HOSTS
    for mid in thread_ids:
        terms = [("HEADER", header, _search_string(mid).decode()) for header in headers]
        searches = terms if one_per_header else [("OR", "OR", *itertools.chain(*terms))]
        for criteria in searches:
            with contextlib.suppress(imaplib.IMAP4.error):
                status, data = conn.uid("SEARCH", *criteria)
                if status == "OK" and data[0]:
                    all_uids.update(data[0].split())

    thread_emails = []
    for uid in all_uids:
        uid_str = uid.decode("utf-8") if isinstance(uid, bytes) else str(uid)
        try:
            mail = read_email(conn, uid_str, folder)
            thread_emails.append(mail)
        except EmailNotFoundError:
            continue

    thread_emails.sort(key=lambda e: e.date)
    return thread_emails


def list_drafts(conn: imaplib.IMAP4_SSL) -> list[EmailSummary]:
    """List all drafts in the Drafts folder."""
    drafts_folder = _find_drafts_folder(conn)

    status, _ = conn.select(f'"{drafts_folder}"', readonly=True)
    if status != "OK":
        raise FolderNotFoundError("Could not select Drafts folder.")

    status, data = conn.uid("SEARCH", "ALL")
    if status != "OK":
        return []

    uid_list = data[0].split() if data[0] else []
    uid_list.reverse()

    drafts = []
    for uid in uid_list:
        summary = _fetch_email_summary(conn, uid)
        if summary:
            drafts.append(summary)

    return drafts


def create_draft(
    conn: imaplib.IMAP4_SSL,
    email_address: str,
    full_name: str,
    to: list[str],
    subject: str,
    body: str,
    body_type: str = "text/plain",
    cc: list[str] | None = None,
) -> dict:
    """Save an email draft to the Drafts folder."""
    body_type = _validate_body_type(body_type)
    drafts_folder = _find_drafts_folder(conn)

    msg = email.message.EmailMessage()
    if full_name:
        safe_name = _sanitize_header_value(full_name.strip())
        msg["From"] = email.headerregistry.Address(display_name=safe_name, addr_spec=email_address)
    else:
        msg["From"] = email_address
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)

    if body_type == "text/html":
        msg.set_content(body, subtype="html", charset="utf-8")
    else:
        msg.set_content(body, charset="utf-8")

    raw_msg = msg.as_bytes()

    status, _ = conn.append(
        f'"{drafts_folder}"',
        "\\Draft",
        None,
        raw_msg,
    )

    if status != "OK":
        raise MailIMAPError("Failed to save draft.")

    return {"success": True, "message": "Draft saved successfully."}


def download_attachment(
    conn: imaplib.IMAP4_SSL,
    uid: str,
    part_number: str,
    folder: str = "INBOX",
) -> AttachmentContent:
    """Download an email attachment by UID and part number.

    Returns the attachment content as base64-encoded string.
    """
    uid = _sanitize_uid(uid)
    folder = _sanitize_folder_name(folder)
    status, _ = conn.select(_mailbox(folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError(f"Folder '{folder}' not found.")

    status, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
    if status != "OK" or not data or data[0] is None:
        raise EmailNotFoundError(f"Email with UID '{uid}' not found in folder '{folder}'.")

    raw_email = b""
    for part_data in data:
        if isinstance(part_data, tuple):
            raw_email = part_data[1] if isinstance(part_data[1], bytes) else part_data[1].encode()

    msg = email.message_from_bytes(raw_email)

    for counter, part in enumerate(msg.walk(), start=1):
        if str(counter) == part_number:
            payload = _part_bytes(part)
            if payload is None:
                raise MailIMAPError(f"Attachment part '{part_number}' has no content.")

            if len(payload) > MAX_ATTACHMENT_BYTES:
                raise MailIMAPError(
                    f"Attachment size ({len(payload):,} bytes) exceeds the "
                    f"{MAX_ATTACHMENT_BYTES:,}-byte limit."
                )

            filename = part.get_filename()
            if filename:
                filename = decode_header_value(filename)
            else:
                filename = f"attachment_{part_number}"

            content_type = part.get_content_type()
            content_b64 = base64.b64encode(payload).decode("ascii")

            return AttachmentContent(
                filename=filename,
                content_type=content_type,
                size=len(payload),
                content_base64=content_b64,
            )

    raise MailIMAPError(
        f"Attachment part '{part_number}' not found in email UID '{uid}'. "
        "Check the part_number from read_email attachment metadata."
    )


# --- Mailbox organization ---


def _server_reason(data: list) -> str:
    first = data[0] if data else b""
    return first.decode("utf-8", errors="replace") if isinstance(first, bytes) else str(first)


def _select_writable(conn: imaplib.IMAP4_SSL, folder: str) -> None:
    status, _ = conn.select(_mailbox(folder))
    if status != "OK":
        raise FolderNotFoundError(
            f"Folder '{folder}' not found. Use list_folders to see available folders."
        )


def create_folder(conn: imaplib.IMAP4_SSL, name: str) -> dict:
    """Create a mailbox folder."""
    status, data = conn.create(_mailbox(name))
    if status != "OK":
        raise MailIMAPError(f"Failed to create folder '{name}': {_server_reason(data)}")
    return {"success": True, "message": f"Folder '{name}' created."}


def move_emails(
    conn: imaplib.IMAP4_SSL, uids: list[str], destination: str, folder: str = "INBOX"
) -> dict:
    """Move emails to another folder."""
    uid_set = _uid_set(uids)
    target = _mailbox(destination)
    _select_writable(conn, folder)
    status, data = conn.uid("MOVE", uid_set, target)
    if status != "OK":
        raise MailIMAPError(
            f"Failed to move to '{destination}': {_server_reason(data)} "
            "Create the folder with create_folder if it does not exist."
        )
    return {
        "success": True,
        "message": f"Server accepted moving {len(uids)} UID(s) from '{folder}' to '{destination}'.",
    }


def mark_read(
    conn: imaplib.IMAP4_SSL, uids: list[str], folder: str = "INBOX", read: bool = True
) -> dict:
    """Set or clear the read flag on emails."""
    uid_set = _uid_set(uids)
    _select_writable(conn, folder)
    status, data = conn.uid(
        "STORE", uid_set, "+FLAGS.SILENT" if read else "-FLAGS.SILENT", "(\\Seen)"
    )
    if status != "OK":
        raise MailIMAPError(f"Failed to update read flag: {_server_reason(data)}")
    state = "read" if read else "unread"
    return {"success": True, "message": f"Server accepted marking {len(uids)} UID(s) as {state}."}


def trash_emails(conn: imaplib.IMAP4_SSL, uids: list[str], folder: str = "INBOX") -> dict:
    """Move emails to the Trash folder. Nothing is expunged, so they can be restored."""
    trash = _find_folder_by_role(
        conn, "\\Trash", ["Trash", "Deleted Messages", "휴지통", "지운편지함"]
    )
    return move_emails(conn, uids, trash, folder)
