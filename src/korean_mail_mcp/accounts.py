"""Mail accounts read from environment variables.

Without ``MAIL_ACCOUNTS`` the server has one account, called ``default``, from ``MAIL_ADDRESS``,
``MAIL_PASSWORD`` and ``MAIL_FULL_NAME``.

With ``MAIL_ACCOUNTS=naver-a,daum`` it has one account per listed name, and each name reads its own
``MAIL_<NAME>_ADDRESS``, ``MAIL_<NAME>_PASSWORD`` and ``MAIL_<NAME>_FULL_NAME`` (the name in upper
case, with ``-`` written as ``_``): ``MAIL_NAVER_A_ADDRESS`` for ``naver-a``. The plain
``MAIL_ADDRESS`` variables are then ignored.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_ACCOUNT = "default"

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}")


@dataclass(frozen=True)
class Account:
    """One mail account. The password stays out of repr so that logs cannot show it."""

    name: str
    address: str
    password: str = field(repr=False)
    full_name: str = ""


def _variable_key(name: str) -> str:
    return name.upper().replace("-", "_")


def load_accounts(environ: Mapping[str, str] | None = None) -> dict[str, Account]:
    """Read the accounts, in the order they are listed, keyed by name.

    Raises:
        ValueError: If the configuration is missing a required variable or is malformed.
    """
    if environ is None:
        environ = os.environ

    listed = environ.get("MAIL_ACCOUNTS", "").strip()
    if not listed:
        address = environ.get("MAIL_ADDRESS", "")
        password = environ.get("MAIL_PASSWORD", "")
        if not address or not password:
            raise ValueError(
                "Missing required environment variables: "
                "MAIL_ADDRESS and MAIL_PASSWORD must be set."
            )
        full_name = environ.get("MAIL_FULL_NAME", "")
        return {DEFAULT_ACCOUNT: Account(DEFAULT_ACCOUNT, address, password, full_name)}

    names = [name.strip() for name in listed.split(",") if name.strip()]
    if not names:
        raise ValueError("MAIL_ACCOUNTS is set but lists no account name.")

    accounts: dict[str, Account] = {}
    keys: dict[str, str] = {}
    for name in names:
        if not _NAME.fullmatch(name):
            raise ValueError(
                f"Invalid account name '{name}' in MAIL_ACCOUNTS: use letters, digits, '-' and "
                "'_', start with a letter, and keep it within 32 characters."
            )
        key = _variable_key(name)
        if key in keys:
            raise ValueError(
                f"Account names '{keys[key]}' and '{name}' in MAIL_ACCOUNTS read the same "
                f"variables (MAIL_{key}_*); give them names that differ in more than '-' or case."
            )
        keys[key] = name

        address_variable = f"MAIL_{key}_ADDRESS"
        password_variable = f"MAIL_{key}_PASSWORD"
        address = environ.get(address_variable, "")
        password = environ.get(password_variable, "")
        missing = [
            variable
            for variable, value in ((address_variable, address), (password_variable, password))
            if not value
        ]
        if missing:
            raise ValueError(
                f"Missing required environment variables for account '{name}': "
                f"{' and '.join(missing)} must be set."
            )
        full_name = environ.get(f"MAIL_{key}_FULL_NAME", "")
        accounts[name] = Account(name, address, password, full_name)
    return accounts
