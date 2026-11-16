# CLAUDE.md

## Project Overview

네이버·다음·카카오 메일 MCP 서버 (Python, mcp 2.x의 MCPServer).
chanmuzi/naver-mail-mcp의 fork. 서버 프로세스 하나가 계정 하나를 맡고, 접속 서버는 `MAIL_ADDRESS`의 도메인으로 정한다(`providers.py`).

## Tools (13개)

`get_profile`, `search_emails`, `read_email`, `read_thread`, `list_folders`, `create_draft`, `list_drafts`, `send_email`, `download_attachment`, `create_folder`, `move_emails`, `mark_read`, `trash_emails`

## Security

보안 리뷰 완료 — 아래 패턴이 적용되어 있으며 반드시 유지할 것:
- IMAP injection 방지
- Header injection 방지
- DoS 방지 (첨부파일 크기 제한 등)

## Testing

- 단위 테스트: `uv run pytest` (계정 불필요, CI에서 Python 3.10–3.15 × 3개 OS로 실행)
- 정적 검사: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`
- 통합 테스트: `uv run python -m tests.test_integration` (실제 계정 필요, CI에서 돌리지 않음)
- `send_email`과 정리 도구(`move_emails`, `mark_read`, `trash_emails`, `create_folder`)는 메일함을 바꾸므로 통합 테스트에 넣지 않는다.
- 다음·카카오와 정리 도구는 실제 계정으로 검증되지 않았다. 검증하면 이 줄을 고친다.
