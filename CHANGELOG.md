# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-11-18

### Added

- `read_email` and `read_thread` take an optional `max_chars`, which cuts `body_text` and `body_html` of each message to that many characters and sets `truncated` when it cut anything; without it the whole body is returned as before. It limits what is returned, not what is downloaded, because the server still sends the whole message
- `read_email` and `read_thread` return checks on the sender, read from the headers: `reply_to` and `reply_to_differs` (a `Reply-To` on a domain unrelated to `From`'s), `list_unsubscribe` (bulk mail) and `authentication`, the `spf`, `dkim` and `dmarc` verdicts that the provider recorded. Naver records all three in `Authentication-Results`; Daum and Kakao record only `Received-SPF`, so they give `spf` alone (checked on the newest inbox messages of the three accounts: 80 from Naver and Daum, 56 from Kakao). A line counts only when it names the provider (`mx.naver.com`, `mx.daum.net`, `kakao.com`), because a sender or a relay can write such lines too: one Daum message carried only the `Authentication-Results` of the SparkPost server that had relayed it. The verdict words are limited to the RFC 8601 set, so no free text from a sender reaches the result

### Changed

- `LICENSE` and `pyproject.toml` credit M1nu0x0 next to chanmuzi. The original MIT notice, `Copyright (c) 2026 chanmuzi`, stays as it was, and a second line covers the changes made in this repository

### Fixed

- `send_email` adds a `Date` header to the mail it sends. Daum's and Kakao's SMTP servers do not add one, so mail sent through them arrived without a date, while Naver's server does and `smtplib` does not
- A header with a malformed encoded word no longer fails the call that reads it. `email.header.decode_header` raises `HeaderParseError` for a base64 word that is one character past a multiple of four, and one Daum message with such a Subject made `read_email` of that message, every `search_emails` page that listed it and every text-filtered search of its folder fail; `decode_header_value` falls back to the policy parser, which decodes the words it can and keeps the rest as text

## [0.2.0] - 2026-11-17

### Added

- A Claude Code plugin, `korean-mail-mcp`, in `plugins/korean-mail-mcp/`, and a marketplace of the same name in `.claude-plugin/marketplace.json` that points at it, so the server installs with `/plugin install korean-mail-mcp --marketplace M1nu0x0/korean-mail-mcp`; it follows the layout of M1nu0x0's other plugin repositories
- The plugin's `.mcp.json` starts the server with `uvx` from this repository and passes it seven `userConfig` options: an address and a password for each of Naver, Daum and Kakao, and one display name for all of them. It lists the three services in `MAIL_ACCOUNTS=naver?,daum?,kakao?`, so one server holds up to one account per service and a service left empty is skipped; with a single service filled in, the server works as before. Claude Code asks for the options when the plugin is enabled, and the passwords are kept as sensitive values instead of in `settings.json`
- `tests/test_plugin.py`, run by `uv run pytest`, which fails when the marketplace, `plugin.json`, `.mcp.json`, `pyproject.toml` and `server.py` disagree about the version, the console script, the environment variables or the options, and loads the accounts from the environment that the plugin would give the server
- A `Plugin` workflow that validates the marketplace and the plugin with `claude plugin validate` on Ubuntu, Windows and macOS, builds the site and checks its sitemap's `lastmod` on pull requests; it also runs daily, because Claude Code can change how plugins and their MCP servers are loaded
- A `Release check` workflow that fails a `vX.Y.Z` tag unless it matches the version in both `plugin.json` and `pyproject.toml`
- A GitHub Pages site in Korean, English and Japanese, built with [claude-plugin-site](https://github.com/M1nu0x0/claude-plugin-site) v0.1.1 and published by a `Pages` workflow
- READMEs in English and Japanese, and a Korean README that now starts with the plugin install
- One server can serve several accounts. `MAIL_ACCOUNTS=naver-a,daum` lists their names, and each name reads its own `MAIL_<NAME>_ADDRESS`, `MAIL_<NAME>_PASSWORD` and `MAIL_<NAME>_FULL_NAME`; without `MAIL_ACCOUNTS` the server works as before with `MAIL_ADDRESS`, `MAIL_PASSWORD` and `MAIL_FULL_NAME`, and its results are unchanged. Every tool takes an optional `account`. `get_profile`, `search_emails`, `list_folders` and `list_drafts` run on every account when it is left out and return the results per account, with a failing account reporting an `error` instead of stopping the others; the other nine tools, including `send_email`, require it when more than one account is configured, so that mail never leaves from or is deleted in an account by default
- `tests/test_accounts.py`, run by `uv run pytest`, for the account configuration, the choice of account and the reading of every account
- A name in `MAIL_ACCOUNTS` can end in `?`, as in `MAIL_ACCOUNTS=naver?,daum?`, to make the account optional: it is skipped when its address is empty, even if a password is still set, and an address without a password, or no account left after the skipping, is an error. The plugin lists its three services this way, and because `claude plugin configure` cannot clear a stored sensitive value, clearing the address is what turns a service off
- The READMEs and the site's FAQ show how to register accounts by hand with `claude mcp add`: each account needs its own server name, such as `naver-mail-a` and `naver-mail-b` for two Naver accounts, because the service comes from the domain of the address; the plugin is turned off with `claude plugin disable korean-mail-mcp` when only those servers are used
- Dependabot updates for GitHub Actions, the uv dependencies and the site, each waiting 7 days after a release (`cooldown: default-days: 7`), so a malicious release that is pulled within a week never reaches a pull request; security updates skip the wait

### Fixed

- `read_thread` on Daum and Kakao sends one ORed `SEARCH` per Message-ID instead of three, since those servers scan the whole folder on every search; a lone message took 43 s on Daum and 22 s on Kakao and now takes 8.5 s and 5.2 s. Naver answers 0 to ORed `HEADER` keys, so it keeps one search per header
- A failed call on one account shows the model why: a missing folder, a server error or a 30-second timeout used to reach it as a bare `Error executing tool`, because the SDK hides the message of anything but a `ToolError`. Unexpected errors still show no detail
