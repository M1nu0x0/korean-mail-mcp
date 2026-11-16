"""Mail MCP server for Naver, Daum and Kakao.

One server process serves the accounts listed in its environment (see accounts.py), one account
by default; the provider of each is chosen by the email domain.
All logging goes to stderr — stdout is reserved for MCP JSON-RPC.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import imap_client, smtp_client
from .accounts import Account, load_accounts
from .models import to_dict
from .providers import hosts_for

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s - %(message)s")
logger = logging.getLogger("korean-mail-mcp")

mcp = MCPServer("korean-mail-mcp")


def _unset(account: str | None) -> bool:
    return account is None or not account.strip()


def _pick(accounts: dict[str, Account], account: str | None) -> Account:
    """The account a call is for. With a single account the name may be left out.

    A wrong or missing name is a ToolError so that the model gets the message and the names to
    choose from; the SDK shows it nothing of any other exception.
    """
    wanted = (account or "").strip()
    if not wanted:
        if len(accounts) == 1:
            return next(iter(accounts.values()))
        raise ToolError(
            "account is required because more than one account is configured. "
            f"Choose one of: {', '.join(accounts)}."
        )
    if wanted in accounts:
        return accounts[wanted]
    for name, chosen in accounts.items():
        if name.casefold() == wanted.casefold():
            return chosen
    raise ToolError(f"Unknown account '{wanted}'. Choose one of: {', '.join(accounts)}.")


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _run_one(account: str | None, call: Callable[[Account], Any]) -> str:
    """Run a call on one account. Several accounts: the name is required and the result names it.

    An object result gets an ``account`` field, and a list is wrapped as ``{"account", "result"}``.
    """
    accounts = load_accounts()
    chosen = _pick(accounts, account)
    payload = call(chosen)
    if len(accounts) > 1:
        if isinstance(payload, dict):
            payload = {"account": chosen.name, **payload}
        else:
            payload = {"account": chosen.name, "result": payload}
    return _dump(payload)


def _run_each(account: str | None, call: Callable[[Account], Any]) -> str:
    """Run a read-only call on one account, or on every account when the name is left out.

    The accounts run side by side, and one that fails reports its error without stopping the rest.
    """
    accounts = load_accounts()
    if not _unset(account) or len(accounts) == 1:
        return _run_one(account, call)

    def attempt(chosen: Account) -> dict[str, Any]:
        entry: dict[str, Any] = {"account": chosen.name, "address": chosen.address}
        try:
            entry["result"] = call(chosen)
        except (imap_client.MailIMAPError, smtp_client.MailSMTPError, ValueError) as error:
            # anticipated failures carry messages written to be read, so they go to the model
            # here, even though the SDK hides them from the model on a single-account call
            logger.warning("Account '%s' failed: %s", chosen.name, error)
            entry["error"] = str(error)
        except Exception:  # one crashing account must not hide the others
            logger.exception("Account '%s' crashed", chosen.name)
            entry["error"] = "Unexpected error. See the server log."
        return entry

    with ThreadPoolExecutor(max_workers=len(accounts)) as pool:
        return _dump(list(pool.map(attempt, accounts.values())))


@mcp.tool()
def get_profile(account: str | None = None) -> str:
    """Get the account profile: email address, display name, total messages, and unread count.

    Args:
        account: Account name. Omit it to run on every configured account; the results
            are then listed per account, and an account that fails reports an error without
            stopping the others. With a single account the name can always be left out.

    Returns:
        JSON string with the profile.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return to_dict(imap_client.get_profile(conn, acc.address, acc.full_name))

    return _run_each(account, call)


@mcp.tool()
def search_emails(
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
    account: str | None = None,
) -> str:
    """Search emails in a folder with optional filters.

    text_search chooses how sender, recipient and subject are matched:
    - "local": the server sends the headers and they are compared here as decoded
      text. Exact and case-insensitive on every provider. Takes a few seconds on Daum
      and Kakao; on Naver about 50 ms per message in the folder (minutes for thousands).
    - "server": the server does the matching. On Naver it takes about a second, ignores
      case, and returns only the newest 1,000 matches. A text of more than 7 letters is
      narrowed on the server and then checked here (about 50 ms per candidate, up to
      about 50 s for 1,000), and the 1,000 cut-off can then hide real matches. On Daum
      and Kakao it is approximate: a few real matches are missed, more so for
      one-character Korean words.
    - "auto" (default): "server" on Naver, "local" on Daum and Kakao.

    Daum shows only the newest 400 messages of a folder, whatever the mode.

    Args:
        folder: Mailbox folder to search in (default: INBOX).
        sender: Filter by sender email or name.
        recipient: Filter by recipient email or name.
        subject: Filter by subject keyword.
        date_from: Filter emails after this date (DD-Mon-YYYY, e.g., 01-Jan-2026).
        date_to: Filter emails before this date (DD-Mon-YYYY, e.g., 31-Dec-2026).
        is_read: Filter by read status (true=read, false=unread, null=all).
        page: Page number for pagination (default: 1).
        page_size: Number of results per page (default: 20).
        text_search: "auto" (default), "server" or "local"; see above.
        account: Account name. Omit it to run on every configured account; the results
            are then listed per account, and an account that fails reports an error without
            stopping the others. With a single account the name can always be left out.
        With several accounts, folder, page and page_size apply to each account on its own,
        and a UID belongs to the account it is listed under.

    Returns:
        JSON string with search results including email summaries and pagination info.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return to_dict(
                imap_client.search_emails(
                    conn,
                    folder=folder,
                    sender=sender,
                    recipient=recipient,
                    subject=subject,
                    date_from=date_from,
                    date_to=date_to,
                    is_read=is_read,
                    page=page,
                    page_size=page_size,
                    text_search=text_search,
                )
            )

    return _run_each(account, call)


@mcp.tool()
def read_email(uid: str, folder: str = "INBOX", account: str | None = None) -> str:
    """Read a full email by UID.

    Args:
        uid: The unique identifier of the email.
        folder: Mailbox folder containing the email (default: INBOX).
        account: Account name. Required when more than one account is configured; a UID
            belongs to the account it was listed under.

    Returns:
        JSON string with headers, body (text and HTML), and attachment metadata.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return to_dict(imap_client.read_email(conn, uid, folder))

    return _run_one(account, call)


@mcp.tool()
def read_thread(message_id: str, folder: str = "INBOX", account: str | None = None) -> str:
    """Read an email thread by Message-ID.

    Finds all related emails via References and In-Reply-To headers.

    Args:
        message_id: The Message-ID header value of any email in the thread.
        folder: Mailbox folder to search in (default: INBOX).
        account: Account name. Required when more than one account is configured.

    Returns:
        JSON string with a list of all emails in the thread, sorted by date.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return [to_dict(e) for e in imap_client.read_thread(conn, message_id, folder)]

    return _run_one(account, call)


@mcp.tool()
def list_folders(account: str | None = None) -> str:
    """List all mailbox folders with message counts.

    Args:
        account: Account name. Omit it to run on every configured account; the results
            are then listed per account, and an account that fails reports an error without
            stopping the others. With a single account the name can always be left out.

    Returns:
        JSON string with a list of folders, each containing name, message count, and unseen count.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return [to_dict(f) for f in imap_client.list_folders(conn)]

    return _run_each(account, call)


@mcp.tool()
def create_draft(
    to: list[str],
    subject: str,
    body: str,
    body_type: str = "text/plain",
    cc: list[str] | None = None,
    account: str | None = None,
) -> str:
    """Save an email draft to the Drafts folder.

    Args:
        to: List of recipient email addresses.
        subject: Email subject line.
        body: Email body content.
        body_type: Content type — 'text/plain' (default) or 'text/html'.
        cc: Optional list of CC email addresses.
        account: Account name. Required when more than one account is configured.

    Returns:
        JSON string confirming draft was saved.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return imap_client.create_draft(
                conn, acc.address, acc.full_name, to, subject, body, body_type, cc
            )

    return _run_one(account, call)


@mcp.tool()
def list_drafts(account: str | None = None) -> str:
    """List all drafts in the Drafts folder.

    Args:
        account: Account name. Omit it to run on every configured account; the results
            are then listed per account, and an account that fails reports an error without
            stopping the others. With a single account the name can always be left out.

    Returns:
        JSON string with a list of draft email summaries.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return [to_dict(d) for d in imap_client.list_drafts(conn)]

    return _run_each(account, call)


@mcp.tool()
def send_email(
    to: list[str],
    subject: str,
    body: str,
    body_type: str = "text/plain",
    cc: list[str] | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
    account: str | None = None,
) -> str:
    """Send an email via SMTP.

    Args:
        to: List of recipient email addresses.
        subject: Email subject line.
        body: Email body content.
        body_type: Content type — 'text/plain' (default) or 'text/html'.
        cc: Optional list of CC email addresses.
        in_reply_to: Message-ID of the email being replied to (for replies).
        references: List of Message-IDs in the thread (for replies).
        account: Account name to send from. Required when more than one account is
            configured, so that mail never leaves from an account by default.

    Returns:
        JSON string confirming email was sent.
    """

    def call(acc: Account) -> Any:
        return smtp_client.send_email(
            acc.address,
            acc.password,
            acc.full_name,
            to,
            subject,
            body,
            body_type,
            cc,
            in_reply_to,
            references,
        )

    return _run_one(account, call)


@mcp.tool()
def download_attachment(
    uid: str, part_number: str, folder: str = "INBOX", account: str | None = None
) -> str:
    """Download an email attachment by UID and MIME part number.

    The part_number can be found in the attachments list from read_email.

    Args:
        uid: The unique identifier of the email containing the attachment.
        part_number: The MIME part number of the attachment (from read_email response).
        folder: Mailbox folder containing the email (default: INBOX).
        account: Account name. Required when more than one account is configured; a UID
            belongs to the account it was listed under.

    Returns:
        JSON string with attachment metadata and base64-encoded content.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return to_dict(imap_client.download_attachment(conn, uid, part_number, folder))

    return _run_one(account, call)


@mcp.tool()
def create_folder(name: str, account: str | None = None) -> str:
    """Create a mailbox folder. Folders are how these providers label mail.

    Args:
        name: Folder name, e.g. '영수증'.
        account: Account name. Required when more than one account is configured.

    Returns:
        JSON string confirming the folder was created.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return imap_client.create_folder(conn, name)

    return _run_one(account, call)


@mcp.tool()
def move_emails(
    uids: list[str], destination: str, folder: str = "INBOX", account: str | None = None
) -> str:
    """Move emails to another folder. An email lives in exactly one folder.

    Args:
        uids: UIDs of the emails to move (from search_emails), at most 500.
        destination: Target folder name or raw_name from list_folders.
        folder: Folder the emails are in now (default: INBOX).
        account: Account name. Required when more than one account is configured.

    Returns:
        JSON string saying the server accepted the move. The server also answers OK
        for a UID that does not exist, so the number of emails actually moved is not
        reported; search the destination folder to confirm. UIDs may change after a
        move; search again before acting on the moved emails. Daum shows only the
        newest 400 emails of a folder, so older ones cannot be moved by UID.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return imap_client.move_emails(conn, uids, destination, folder)

    return _run_one(account, call)


@mcp.tool()
def mark_read(
    uids: list[str], folder: str = "INBOX", read: bool = True, account: str | None = None
) -> str:
    """Mark emails as read or unread.

    Args:
        uids: UIDs of the emails (from search_emails), at most 500.
        folder: Folder containing the emails (default: INBOX).
        read: True marks as read (default), False marks as unread.
        account: Account name. Required when more than one account is configured.

    Returns:
        JSON string confirming the change.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return imap_client.mark_read(conn, uids, folder, read)

    return _run_one(account, call)


@mcp.tool()
def trash_emails(uids: list[str], folder: str = "INBOX", account: str | None = None) -> str:
    """Move emails to the Trash folder. They are not permanently deleted.

    Args:
        uids: UIDs of the emails (from search_emails), at most 500.
        folder: Folder containing the emails (default: INBOX).
        account: Account name. Required when more than one account is configured.

    Returns:
        JSON string confirming the move to Trash.
    """

    def call(acc: Account) -> Any:
        with imap_client.imap_connection(acc.address, acc.password) as conn:
            return imap_client.trash_emails(conn, uids, folder)

    return _run_one(account, call)


def main():
    """Entry point for the MCP server."""
    try:
        accounts = load_accounts()
    except ValueError as e:
        sys.exit(str(e))
    for account in accounts.values():
        try:
            hosts_for(account.address)
        except ValueError as e:
            sys.exit(f"Account '{account.name}': {e}" if len(accounts) > 1 else str(e))

    logger.info("Starting mail MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
