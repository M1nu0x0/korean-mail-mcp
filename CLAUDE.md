# CLAUDE.md

## Project Overview

네이버·다음·카카오 메일 MCP 서버 (Python, mcp 2.x의 MCPServer).
chanmuzi/naver-mail-mcp의 fork. 서버 프로세스 하나가 계정 하나를 맡고, 접속 서버는 `MAIL_ADDRESS`의 도메인으로 정한다(`providers.py`).

## Tools (13개)

`get_profile`, `search_emails`, `read_email`, `read_thread`, `list_folders`, `create_draft`, `list_drafts`, `send_email`, `download_attachment`, `create_folder`, `move_emails`, `mark_read`, `trash_emails`

## Plugin

Claude Code 플러그인이기도 하다. 레이아웃은 M1nu0x0의 다른 plugin 레포(claude-utf8-guard 등)를 따른다.

- `.claude-plugin/marketplace.json`이 `plugins/korean-mail-mcp/`를 가리킨다. 플러그인 이름은 `claude-`로 시작하면 안 된다(`claude plugin validate`가 예약어로 막음).
- `plugins/korean-mail-mcp/.mcp.json`은 `uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp`로 서버를 띄우고, `userConfig` 세 개(`mail_address`, `mail_password`, `mail_full_name`)를 `MAIL_ADDRESS`, `MAIL_PASSWORD`, `MAIL_FULL_NAME`으로 넘긴다. 서버가 읽는 환경변수를 바꾸면 `.mcp.json`, `plugin.json`, README 3종, `site/src/site.json`도 같이 고친다. `tests/test_plugin.py`가 어긋남을 잡는다.
- 서버는 버전에 고정하지 않고 기본 브랜치에서 가져온다. `pyproject.toml`과 `plugin.json`의 `version`은 항상 같게 올리고, 릴리스 태그(`vX.Y.Z`)와도 같아야 한다(`release.yml`이 확인).
- `site/`는 GitHub Pages 사이트(Astro, 한국어·영어·일본어). 문구는 `site/src/site.json`에 있고, 바꾸면 `updated`를 그날 날짜로 바꾼다. `ask`, `answer`, `ogImageLine`, `ogImageText`를 바꾸면 `npm run og`로 `site/public/images/og*.png`를 다시 만든다.
- 설정, 도구, 제공자별 동작이 바뀌면 `README.md`, `README.en.md`, `README.ja.md`, `site/src/site.json`의 세 언어를 함께 고친다.

## Security

아래 패턴은 반드시 유지할 것. 첨부 크기 제한은 메시지 전체를 받은 뒤에 검사하므로, 큰 메시지의 메모리 사용은 막지 못한다:
- IMAP injection 방지
- Header injection 방지
- DoS 방지 (첨부파일 크기 제한 등)

## Testing

- 단위 테스트: `uv run pytest` (계정 불필요, `tests/test_unit.py`와 `tests/test_plugin.py`, CI에서 Python 3.10–3.15 × 3개 OS로 실행)
- 정적 검사: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`
- 플러그인 검사: `claude plugin validate .`, `claude plugin validate plugins/korean-mail-mcp`, `cd site && npm ci && npm run build` (`plugin.yml`이 CI와 매일 돌림). 플러그인 파일끼리의 일치는 `uv run pytest`의 `tests/test_plugin.py`가 본다.
- 통합 테스트: `uv run python -m tests.test_integration` (실제 계정 필요, CI에서 돌리지 않음)
- `send_email`과 정리 도구(`move_emails`, `mark_read`, `trash_emails`, `create_folder`)는 메일함을 바꾸므로 통합 테스트에 넣지 않는다.
- 2026-11-16에 다음·카카오 실제 계정으로 통합 테스트 9개와 한글 검색을 검증했다. 같은 날 정리 도구 4개도 세 계정에서 시험 메일 한 통의 왕복(읽음 표시, 한글 이름 폴더 생성, 이동, 휴지통)으로 검증했다. 여러 통을 한 번에 옮기는 경우와 없는 폴더로 옮기는 오류 경로는 실제 계정으로 검증하지 않았다.

## Provider quirks

- 다음·카카오는 `UID FETCH ... RFC822`에 데이터 없이 OK를 준다. 본문은 `BODY.PEEK[]`로 가져온다.
- 다음·카카오는 비ASCII `SEARCH`에 항상 0건을 준다. From/To/Subject 필터는 헤더를 받아 로컬에서 대조한다(`_filter_by_headers`).
- 다음·카카오는 `SPECIAL-USE`를 알리지 않는다. 휴지통은 `Deleted Messages`, 임시보관함은 `Drafts`라는 이름으로 찾는다.
- 다음·카카오 로그인은 전체 주소와 ID 둘 다 된다.
- 다음은 폴더마다 최근 400통만 IMAP으로 보인다. 그보다 오래된 메일은 UID로도 닿지 않는다.
- 다음·카카오의 `SEARCH`는 디코딩하지 않은 헤더 원문 바이트와 대조한다(`utf-8` 검색에 인코딩된 제목 193통이 걸림). 본문 검색(`BODY`, `TEXT`)은 항상 0건이다.
- 네이버는 헤더 조회가 메일당 약 50ms로 느리다(411통 21초, 5,000통 411초). 그래서 `text_search="auto"`는 네이버만 서버 `SEARCH`로 텍스트를 거른다(`providers.SERVER_TEXT_SEARCH_HOSTS`).
- `search_emails`의 `text_search`는 `auto`·`server`·`local` 중 고른다. 다음·카카오의 `server`는 한글의 인코딩 형태(`_encoded_forms`)를 원문에서 찾는 근사 검색이다(다음 98건 중 95건, 카카오 65건 중 64건, 오탐 0건).
- 네이버 `SEARCH`는 디코딩한 헤더와 대조하지만 모든 키(`SUBJECT`, `FROM`, `HEADER`, charset 유무)에서 대소문자를 구분하고 `SEARCH=FUZZY`가 없다. OR는 1,024개까지 받고 조건 하나당 7–10ms다. 그래서 대소문자 조합을 전부 OR로 보낸다(`_casings`, 영문자 7자까지 128개). 더 긴 검색어는 조각을 AND로 묶어 후보를 좁히고 그 후보만 로컬에서 확인한다. 필드가 여럿이면 OR 항 합계가 1,024개를 넘지 않게 필드당 조각 수를 줄인다(`MAX_SERVER_TERMS`). 로컬 확인에서 응답이 빠진 UID는 작은 묶음으로 한 번 더 조회한다(`HEADER_RETRY_BATCH`). 텍스트 조건이 있으면 최신 1,000건까지만 돌려준다. 날짜나 UID 조건을 더해도 그보다 오래된 일치 건은 나오지 않는다.
- 네이버는 웹 설정의 "IMAP 동기화 메일 제한"(최대 5,000통)만큼만 폴더가 보인다.
- 2026-11-16에 네이버 실제 계정으로 통합 테스트 9개를 검증했다.
