# korean-mail-mcp

[![release](https://img.shields.io/github/v/release/M1nu0x0/korean-mail-mcp)](https://github.com/M1nu0x0/korean-mail-mcp/releases)
[![CI](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/ci.yml)
[![Plugin](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/plugin.yml/badge.svg)](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/plugin.yml)
[![license](https://img.shields.io/github/license/M1nu0x0/korean-mail-mcp)](LICENSE)

[한국어](README.md) | **English** | [日本語](README.ja.md)

A Claude Code plugin and MCP (Model Context Protocol) server that lets Claude use Naver, Daum and Kakao mail.
It is a fork of [chanmuzi/naver-mail-mcp](https://github.com/chanmuzi/naver-mail-mcp) that adds Daum and Kakao support and tools for tidying a mailbox.

One server process serves one account, and the servers it connects to are chosen by the domain of the email address.

**[Website](https://m1nu0x0.github.io/korean-mail-mcp/) · [Releases](https://github.com/M1nu0x0/korean-mail-mcp/releases) · [Changelog](CHANGELOG.md)**

| Domain | IMAP | SMTP |
|--------|------|------|
| `naver.com` | `imap.naver.com` | `smtp.naver.com` |
| `daum.net`, `hanmail.net` | `imap.daum.net` | `smtp.daum.net` |
| `kakao.com` | `imap.kakao.com` | `smtp.kakao.com` |

## Features

| Tool | Description |
|------|-------------|
| `get_profile` | Account profile (address, name, total messages, unread count) |
| `search_emails` | Search by sender, recipient, subject, date and read state, with pagination |
| `read_email` | Read a whole message by UID (headers, body, attachment metadata) |
| `read_thread` | Read a conversation thread by Message-ID |
| `list_folders` | List mailbox folders (with message and unread counts) |
| `create_draft` | Save a new draft in the Drafts folder |
| `list_drafts` | List the drafts in the Drafts folder |
| `send_email` | Send mail over SMTP (new mail or a reply) |
| `download_attachment` | Download an attachment (base64 encoded) |
| `create_folder` | Create a folder (a mailbox of your own) |
| `move_emails` | Move messages to another folder |
| `mark_read` | Mark messages read or unread |
| `trash_emails` | Move messages to the trash (never deletes for good) |

These services have no labels like Gmail's. A message lives in one folder only, so sorting means creating folders and moving mail into them.

## Installation

### Claude Code plugin

At the Claude Code terminal prompt:

```
/plugin install korean-mail-mcp --marketplace M1nu0x0/korean-mail-mcp
```

Answer `y` to `Add marketplace?` and choose the user scope. From a shell:

```sh
claude plugin install korean-mail-mcp --marketplace M1nu0x0/korean-mail-mcp
```

In Claude Desktop, click `+` next to the prompt box → Plugins → Add marketplace, enter `M1nu0x0/korean-mail-mcp`, then add `korean-mail-mcp`. It applies from the next session.

[uv](https://docs.astral.sh/uv/) must be installed so that `uvx` is on your `PATH`. The server runs straight from this repository with `uvx` (it is not published on PyPI), so there is nothing else to install.

When you enable the plugin, Claude Code asks for three values.

| Option | Required | Description |
|--------|----------|-------------|
| Mail address (`mail_address`) | Yes | The full email address. Its domain picks the service |
| IMAP password (`mail_password`) | Yes | The password for IMAP (not the account password). Kept as a sensitive value, not in `settings.json` |
| Display name (`mail_full_name`) | No | The name shown on mail you send. Leave it empty to use the address alone |

How to get the IMAP password is under [Prerequisites](#prerequisites).

The plugin serves one account. For several accounts, or for an MCP client other than Claude Code, register the server by hand as under [MCP Client Configuration](#mcp-client-configuration).

To turn it off run `claude plugin disable korean-mail-mcp`, and to remove it `claude plugin uninstall korean-mail-mcp`.

### Run it directly with uvx

```bash
uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp
```

## MCP Client Configuration

For when you do not use the plugin. Register one server per account.

```json
{
  "mcpServers": {
    "naver-mail": {
      "command": "/absolute/path/to/uvx",
      "args": ["--from", "git+https://github.com/M1nu0x0/korean-mail-mcp", "korean-mail-mcp"],
      "env": {
        "MAIL_ADDRESS": "your_id@naver.com",
        "MAIL_PASSWORD": "your_app_password",
        "MAIL_FULL_NAME": "Your Name"
      }
    },
    "daum-mail": {
      "command": "/absolute/path/to/uvx",
      "args": ["--from", "git+https://github.com/M1nu0x0/korean-mail-mcp", "korean-mail-mcp"],
      "env": {
        "MAIL_ADDRESS": "your_id@daum.net",
        "MAIL_PASSWORD": "your_imap_password"
      }
    }
  }
}
```

> **Note:** Claude Desktop does not inherit the system PATH. Use the **absolute path** of `uvx` as `command`; `which uvx` shows it. The plugin's `.mcp.json` calls `uvx` by name, so if the server fails to start for this reason, register it by hand this way.

## Prerequisites

1. **Python 3.10+** (`uvx` takes care of it)
2. **Turn on IMAP/SMTP** in the mail service
   - Naver: Mail → Settings → POP3/IMAP → use IMAP/SMTP
   - Daum and Kakao: Mail → Settings → IMAP/POP3 → use IMAP
3. Get the **password for IMAP** (not your login password)
   - Naver: My info → Security → 2-step verification → manage application passwords
   - Daum and Kakao: the dedicated password their IMAP settings page shows

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MAIL_ADDRESS` | Yes | The email address. Its domain picks the service |
| `MAIL_PASSWORD` | Yes | The password for IMAP (not the account password) |
| `MAIL_FULL_NAME` | No | Display name on mail you send |

The plugin takes these three as `mail_address`, `mail_password` and `mail_full_name` and passes them to the server as the environment variables above.

## Tools Reference

### get_profile
Get the account profile. No parameters.

### search_emails
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| folder | string | No | INBOX | Folder to search |
| sender | string | No | - | Sender filter |
| recipient | string | No | - | Recipient filter |
| subject | string | No | - | Subject keyword |
| date_from | string | No | - | Start date (DD-Mon-YYYY) |
| date_to | string | No | - | End date (DD-Mon-YYYY) |
| is_read | boolean | No | - | Read state (true/false/null) |
| page | integer | No | 1 | Page number |
| page_size | integer | No | 20 | Results per page (100 at most) |
| text_search | string | No | auto | How sender, recipient and subject are matched: `auto`, `server` or `local` |

How `text_search` behaves (measured on real accounts on 2026-11-16):

| Mode | Naver | Daum and Kakao |
|------|-------|----------------|
| `local` | Exact, ignores case. About 50 ms per message in the folder (about 20 s for 411 messages) | Exact, ignores case. 2 to 5 s |
| `server` | 0.1 to 2 s. Ignores case, returns only the newest 1,000 | Approximate (95 of 98 matches), 2 to 5 s |
| `auto` | `server` | `local` |

- `local` downloads the headers and compares the decoded text.
- Naver's server is case sensitive, so `server` sends every upper/lower-case combination of the text as an OR. A text of more than 7 letters is split into pieces of 7 to narrow the candidates, and only those candidates have their headers downloaded and checked. Checking takes about 50 ms per candidate, so 1,000 candidates take about 50 s, and when the newest-1,000 cap cuts the candidates, real matches can be missed. If long texts are given for sender, recipient and subject together, fewer pieces are sent to the server (at most 1,024 OR terms in all).
- Daum's and Kakao's servers compare against the raw, undecoded header. So `server` looks for the base64 and quoted-printable forms of Korean text, and misses a word that falls across the boundary of an encoded piece.
- Daum shows only the newest 400 messages of each folder, whichever mode is used.

### read_email
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uid | string | Yes | - | Unique ID of the message |
| folder | string | No | INBOX | Folder |

### read_thread
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| message_id | string | Yes | - | Value of the Message-ID header |
| folder | string | No | INBOX | Folder |

### list_folders
List the folders. No parameters.

### create_draft
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| to | array | Yes | - | Recipients |
| subject | string | Yes | - | Subject |
| body | string | Yes | - | Body |
| body_type | string | No | text/plain | text/plain or text/html |
| cc | array | No | - | Cc recipients |

### list_drafts
List the drafts. No parameters.

### send_email
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| to | array | Yes | - | Recipients |
| subject | string | Yes | - | Subject |
| body | string | Yes | - | Body |
| body_type | string | No | text/plain | text/plain or text/html |
| cc | array | No | - | Cc recipients |
| in_reply_to | string | No | - | Message-ID being replied to |
| references | array | No | - | Message-IDs of the thread |

### download_attachment
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uid | string | Yes | - | Unique ID of the message |
| part_number | string | Yes | - | MIME part number (see read_email) |
| folder | string | No | INBOX | Folder |

### create_folder
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| name | string | Yes | - | Folder name |

### move_emails
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uids | array | Yes | - | UIDs of the messages to move (500 at most) |
| destination | string | Yes | - | Destination folder name, or the `raw_name` from `list_folders` |
| folder | string | No | INBOX | Folder the messages are in now |

UIDs can change after a move, so search the destination folder again to check. On Naver, Daum and Kakao they stayed the same in practice.

The response means the server accepted the move request. The server answers OK even for a UID that does not exist, so it does not tell you how many messages were really moved. Search the destination folder to check. Daum shows only the newest 400 messages of each folder, so older mail cannot be moved by UID.

### mark_read
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uids | array | Yes | - | UIDs of the messages (500 at most) |
| folder | string | No | INBOX | Folder |
| read | boolean | No | true | true marks read, false marks unread |

### trash_emails
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uids | array | Yes | - | UIDs of the messages (500 at most) |
| folder | string | No | INBOX | Folder |

### Folder names

`folder` and `destination` accept a Korean name (`영수증`) or the `raw_name` that `list_folders` returns.

## Development

```bash
# Clone and install
git clone https://github.com/M1nu0x0/korean-mail-mcp.git
cd korean-mail-mcp
uv sync

# Set credentials
cp .env.example .env
# Edit .env with your credentials

# Static checks and unit tests (no account needed)
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest

# Integration tests against the real mail server (needs .env)
uv run python -m tests.test_integration

# The plugin and its site
claude plugin validate .
claude plugin validate plugins/korean-mail-mcp
cd site && npm ci && npm run build   # build the site and check it (site/dist)
cd site && npm run dev               # local preview
cd site && npm run og                # make the link-preview image for each language (needs Playwright)
```

`uv run pytest` includes `tests/test_plugin.py`, which fails when the marketplace, `plugin.json`, `.mcp.json`, `pyproject.toml` and `server.py` disagree (version, environment variable names, required options).

The site is built with [Astro](https://astro.build) and the shared kit [claude-plugin-site](https://github.com/M1nu0x0/claude-plugin-site). All of its words are in `site/src/site.json` and the order of its sections is in `site/src/pages/[...lang].astro`. `npm run build` makes a page for each language (`/`, `/ko/`, `/ja/`) and `sitemap.xml`, then checks them as a crawler reads them, and fails if any check breaks. When a change is merged into main, the Pages workflow builds and deploys it (the Pages source in the repository settings must be **GitHub Actions**). When the text changes, set `updated` in `site/src/site.json` to that day's date; CI warns on a pull request if you do not. If you change `ask`, `answer`, `ogImageLine` or `ogImageText`, regenerate `site/public/images/og*.png` with `npm run og` and commit them.

To release a new version, merge a pull request that raises `version` in both `pyproject.toml` and `plugins/korean-mail-mcp/.claude-plugin/plugin.json`, then create a `vX.Y.Z` Release with the same version. When the tag appears, CI checks that it matches both versions. The plugin's `.mcp.json` does not pin the server to a version: it takes the server from the default branch of this repository.

## Layout

```
.claude-plugin/
  marketplace.json      registers this repo as a marketplace
plugins/korean-mail-mcp/
  .claude-plugin/
    plugin.json         plugin manifest, three userConfig options
  .mcp.json             the MCP server definition that starts it with uvx
src/korean_mail_mcp/    the MCP server (Python)
tests/                  unit tests (test_unit.py, test_plugin.py) and integration tests
site/                   GitHub Pages site (Astro): src/site.json translations, src/pages/ page
README.en.md, README.ja.md  translations of the README
```

The plugin lives in `plugins/korean-mail-mcp/` and the marketplace points at it by a relative path, because claude.ai's Add marketplace sometimes does not accept a repository whose root is the plugin itself.

## Troubleshooting

| Error | Solution |
|-------|----------|
| `IMAP authentication failed` | Check the application password. Use an application password, not the account password |
| `Cannot connect to IMAP server` | Check the network and that IMAP is turned on |
| `Missing required environment variables` | Set `MAIL_ADDRESS` and `MAIL_PASSWORD` |
| `Unsupported mail domain` | Check that the address is in a supported domain (`naver.com`, `daum.net`, `hanmail.net`, `kakao.com`) |
| `Folder not found` | Use the `list_folders` tool to see the folder names available |
| `Failed to spawn process` | Use the absolute path of `uvx` as `command` (`which uvx` shows it) |
| The tools do not show after enabling the plugin | Check in a new session, and run `claude plugin list` to see that it is enabled |

## Technical Details

- **IMAP**: port 993 (SSL/TLS)
- **SMTP**: port 465 (SSL)
- **Transport**: stdio (for Claude Desktop and Claude Code)
- **Encoding**: UTF-8, EUC-KR and Modified UTF-7 (folder names) are handled automatically
- **Connection**: a new connection for each tool call (stateless)
- **Attachment limit**: 10 MB (base64 encoded)

## License

MIT
