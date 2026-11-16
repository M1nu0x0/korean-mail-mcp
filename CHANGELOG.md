# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A Claude Code plugin, `korean-mail-mcp`, in `plugins/korean-mail-mcp/`, and a marketplace of the same name in `.claude-plugin/marketplace.json` that points at it, so the server installs with `/plugin install korean-mail-mcp --marketplace M1nu0x0/korean-mail-mcp`; it follows the layout of M1nu0x0's other plugin repositories
- The plugin's `.mcp.json` starts the server with `uvx` from this repository and passes it three `userConfig` options as the `MAIL_ADDRESS`, `MAIL_PASSWORD` and `MAIL_FULL_NAME` environment variables; Claude Code asks for them when the plugin is enabled, and the password is kept as a sensitive value instead of in `settings.json`
- `tests/test_plugin.py`, run by `uv run pytest`, which fails when the marketplace, `plugin.json`, `.mcp.json`, `pyproject.toml` and `server.py` disagree about the version, the console script, the environment variables or the required options
- A `Plugin` workflow that validates the marketplace and the plugin with `claude plugin validate` on Ubuntu, Windows and macOS, builds the site and checks its sitemap's `lastmod` on pull requests; it also runs daily, because Claude Code can change how plugins and their MCP servers are loaded
- A `Release check` workflow that fails a `vX.Y.Z` tag unless it matches the version in both `plugin.json` and `pyproject.toml`
- A GitHub Pages site in Korean, English and Japanese, built with [claude-plugin-site](https://github.com/M1nu0x0/claude-plugin-site) v0.1.1 and published by a `Pages` workflow
- READMEs in English and Japanese, and a Korean README that now starts with the plugin install
- Dependabot updates for GitHub Actions, the uv dependencies and the site, each waiting 7 days after a release (`cooldown: default-days: 7`), so a malicious release that is pulled within a week never reaches a pull request; security updates skip the wait
