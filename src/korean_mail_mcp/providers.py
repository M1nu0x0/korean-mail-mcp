"""Mail server addresses, chosen by the account's email domain."""

from __future__ import annotations

_NAVER = ("imap.naver.com", "smtp.naver.com")
_DAUM = ("imap.daum.net", "smtp.daum.net")
_KAKAO = ("imap.kakao.com", "smtp.kakao.com")

_HOSTS = {
    "naver.com": _NAVER,
    "daum.net": _DAUM,
    "hanmail.net": _DAUM,
    "kakao.com": _KAKAO,
}

# Naver's SEARCH matches decoded headers and answers at once, while fetching headers there
# costs about 50 ms a message (measured: 21 s for 411, 411 s for 5000).
# Daum and Kakao match raw header bytes, so encoded (Korean) subjects never match.
SERVER_TEXT_SEARCH_HOSTS = {"imap.naver.com"}


def hosts_for(email_address: str) -> tuple[str, str]:
    """Return (IMAP host, SMTP host) for an email address."""
    domain = email_address.rpartition("@")[2].lower()
    try:
        return _HOSTS[domain]
    except KeyError:
        raise ValueError(
            f"Unsupported mail domain '{domain}'. Supported: {', '.join(sorted(_HOSTS))}."
        ) from None
