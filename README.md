# korean-mail-mcp

[![release](https://img.shields.io/github/v/release/M1nu0x0/korean-mail-mcp)](https://github.com/M1nu0x0/korean-mail-mcp/releases)
[![CI](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/ci.yml)
[![Plugin](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/plugin.yml/badge.svg)](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/plugin.yml)
[![license](https://img.shields.io/github/license/M1nu0x0/korean-mail-mcp)](LICENSE)

**한국어** | [English](README.en.md) | [日本語](README.ja.md)

네이버·다음·카카오 메일을 Claude에서 쓰게 해 주는 Claude Code 플러그인이자 MCP(Model Context Protocol) 서버입니다.
[chanmuzi/naver-mail-mcp](https://github.com/chanmuzi/naver-mail-mcp)의 fork이며, 다음·카카오 지원과 메일함 정리 도구를 더했습니다.

서버 프로세스 하나는 기본으로 계정 하나를 맡고(`MAIL_ACCOUNTS`로 여러 계정을 맡길 수도 있습니다), 접속할 서버는 이메일 주소의 도메인으로 정합니다.

**[Website](https://m1nu0x0.github.io/korean-mail-mcp/ko/) · [Releases](https://github.com/M1nu0x0/korean-mail-mcp/releases) · [Changelog](CHANGELOG.md)**

| 도메인 | IMAP | SMTP |
|--------|------|------|
| `naver.com` | `imap.naver.com` | `smtp.naver.com` |
| `daum.net`, `hanmail.net` | `imap.daum.net` | `smtp.daum.net` |
| `kakao.com` | `imap.kakao.com` | `smtp.kakao.com` |

## Features

| Tool | Description |
|------|-------------|
| `get_profile` | 계정 프로필 조회 (이메일, 이름, 총 메일 수, 안읽은 수) |
| `search_emails` | 메일 검색 (발신자, 수신자, 제목, 날짜, 읽음 여부) + 페이지네이션 |
| `read_email` | UID로 메일 전체 읽기 (헤더, 본문, 첨부파일 메타정보) |
| `read_thread` | Message-ID 기반 대화 스레드 조회 |
| `list_folders` | 메일함 폴더 목록 조회 (메시지 수, 안읽은 수 포함) |
| `create_draft` | 새 메일 초안을 Drafts 폴더에 저장 |
| `list_drafts` | Drafts 폴더의 초안 목록 조회 |
| `send_email` | SMTP로 메일 발송 (새 메일, 답장) |
| `download_attachment` | 첨부파일 다운로드 (base64 인코딩) |
| `create_folder` | 폴더(내 메일함) 생성 |
| `move_emails` | 메일을 다른 폴더로 이동 |
| `mark_read` | 읽음 / 안읽음 표시 |
| `trash_emails` | 휴지통으로 이동 (영구 삭제하지 않음) |

이 서비스들에는 Gmail의 라벨이 없습니다. 메일 하나는 폴더 하나에만 들어가므로, 분류는 폴더를 만들고 옮기는 방식으로 합니다.

## 설치

### Claude Code 플러그인

Claude Code 터미널 프롬프트에서:

```
/plugin install korean-mail-mcp --marketplace M1nu0x0/korean-mail-mcp
```

`Add marketplace?`에 `y`를 누르고 scope는 user를 고릅니다. 셸에서는 이렇게 설치합니다.

```sh
claude plugin install korean-mail-mcp --marketplace M1nu0x0/korean-mail-mcp
```

Claude Desktop에서는 프롬프트 옆 `+` → Plugins → Add marketplace에 `M1nu0x0/korean-mail-mcp`를 넣고 `korean-mail-mcp`를 추가합니다. 설치한 뒤 새 세션부터 적용됩니다.

[uv](https://docs.astral.sh/uv/)가 설치돼 있어서 `uvx`가 `PATH`에 있어야 합니다. 서버는 이 저장소에서 `uvx`로 바로 실행되고(PyPI에는 배포되어 있지 않음), 따로 설치할 것은 없습니다.

플러그인을 켜면 Claude Code가 일곱 가지를 묻습니다. 쓰는 서비스만 채우고 나머지는 비워 둡니다. 서버 하나가 서비스마다 계정 하나씩, 최대 세 계정을 맡습니다.

| 항목 | 필수 | 설명 |
|------|------|------|
| Naver address (`naver_address`) | No | 네이버 이메일 주소 전체. 비우면 네이버를 쓰지 않음 |
| Naver IMAP password (`naver_password`) | No | 네이버 애플리케이션 비밀번호(계정 비밀번호 아님). `settings.json`이 아니라 민감한 값으로 따로 보관됨 |
| Daum address (`daum_address`) | No | 다음 이메일 주소 전체(`daum.net` 또는 `hanmail.net`). 비우면 다음을 쓰지 않음 |
| Daum IMAP password (`daum_password`) | No | 다음 IMAP용 비밀번호(계정 비밀번호 아님). 민감한 값으로 따로 보관됨 |
| Kakao address (`kakao_address`) | No | 카카오 이메일 주소 전체. 비우면 카카오를 쓰지 않음 |
| Kakao IMAP password (`kakao_password`) | No | 카카오 IMAP용 비밀번호(계정 비밀번호 아님). 민감한 값으로 따로 보관됨 |
| Display name (`mail_full_name`) | No | 보내는 메일에 표시할 이름. 모든 계정에 같이 쓰이고, 비워 두면 주소만 씀 |

IMAP용 비밀번호를 받는 방법은 아래 [Prerequisites](#prerequisites)에 있습니다. 서비스마다 주소와 비밀번호를 둘 다 채웁니다. 주소만 있고 비밀번호가 없으면 서버가 시작하지 않고, 주소를 비운 서비스는 비밀번호가 남아 있어도 건너뜁니다. 서비스를 하나도 채우지 않으면 서버가 시작하지 않습니다. 나중에 바꾸려면 Claude Code에서 `/plugin configure korean-mail-mcp@korean-mail-mcp`를 실행합니다.

계정이 하나뿐이면 지금까지와 똑같이 동작합니다. 둘 이상이면 [Multiple Accounts](#multiple-accounts)처럼 `account` 인자로 계정(`naver`, `daum`, `kakao`)을 가리킵니다. 같은 서비스의 계정이 둘 이상이거나 Claude Code 밖의 MCP 클라이언트에서 쓴다면 아래 [MCP Client Configuration](#mcp-client-configuration)처럼 서버를 직접 등록합니다.

끄려면 `claude plugin disable korean-mail-mcp`, 제거하려면 `claude plugin uninstall korean-mail-mcp`를 실행합니다.

### uvx로 직접 실행

```bash
uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp
```

## MCP Client Configuration

플러그인을 쓰지 않는 경우입니다. 계정마다 서버를 하나씩 등록합니다.

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

Claude Code에서는 `claude mcp add`로 같은 서버를 등록할 수 있습니다. 서버 이름은 계정마다 달라야 하고(같은 이름을 다시 쓰면 `already exists` 오류가 납니다), 서비스는 이름이 아니라 주소의 도메인으로 정해집니다. 같은 서비스의 계정이 둘이면 `naver-mail-a`, `naver-mail-b`처럼 이름을 나눠 붙이세요.

```bash
claude mcp add --scope user naver-mail-a -e MAIL_ADDRESS=a_id@naver.com -e MAIL_PASSWORD=your_app_password -- uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp
claude mcp add --scope user naver-mail-b -e MAIL_ADDRESS=b_id@naver.com -e MAIL_PASSWORD=your_app_password -- uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp
```

도구도 서버별로 나뉘어 보이므로 어느 계정인지는 `get_profile`로 확인합니다. 이 방식에서는 입력한 값이 플러그인의 민감한 값처럼 따로 보관되지 않고 `~/.claude.json`에 그대로 저장됩니다. 직접 등록한 서버만 쓸 거라면 플러그인은 `claude plugin disable korean-mail-mcp`로 끕니다.

> **주의:** Claude Desktop은 시스템 PATH를 상속하지 않습니다. `command`에는 `uvx`의 **절대 경로**를 쓰세요. `which uvx`로 확인할 수 있습니다. 플러그인의 `.mcp.json`은 `uvx`를 이름으로 부르므로, 같은 문제로 서버가 시작되지 않으면 이 방식으로 직접 등록하세요.

## Prerequisites

1. **Python 3.10+** (`uvx`가 알아서 맞춰 줍니다)
2. 메일 서비스에서 **IMAP/SMTP 사용** 설정
   - 네이버: 메일 → 설정 → POP3/IMAP 설정 → IMAP/SMTP 사용
   - 다음·카카오: 메일 → 설정 → IMAP/POP3 → IMAP 사용
3. **IMAP용 비밀번호** 준비 (로그인 비밀번호가 아님)
   - 네이버: 내 정보 → 보안설정 → 2단계 인증 → 애플리케이션 비밀번호 관리
   - 다음·카카오: IMAP 설정 화면에서 안내하는 전용 비밀번호

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MAIL_ADDRESS` | Yes | 이메일 주소. 도메인으로 서비스를 정함 |
| `MAIL_PASSWORD` | Yes | IMAP용 비밀번호 (계정 비밀번호 아님) |
| `MAIL_FULL_NAME` | No | 발신 메일 표시 이름 |
| `MAIL_ACCOUNTS` | No | 여러 계정의 이름 목록. 있으면 위 세 변수 대신 `MAIL_<이름>_*`를 읽음. [Multiple Accounts](#multiple-accounts) 참고 |

플러그인은 `MAIL_ACCOUNTS=naver?,daum?,kakao?`와 서비스별 `MAIL_NAVER_*`, `MAIL_DAUM_*`, `MAIL_KAKAO_*`를 서버에 넘깁니다. `mail_full_name` 옵션은 세 계정의 `MAIL_<이름>_FULL_NAME`에 같은 값으로 들어갑니다.

## Multiple Accounts

서버 하나로 여러 계정을 다루려면 `MAIL_ACCOUNTS`에 계정 이름을 쉼표로 나열하고, 이름마다 `MAIL_<이름>_ADDRESS`, `MAIL_<이름>_PASSWORD`, `MAIL_<이름>_FULL_NAME`(선택)을 줍니다. 이름은 영문자로 시작하는 영문자, 숫자, `-`, `_`이고 32자까지입니다. 변수 이름에서는 이름을 대문자로 바꾸고 `-`를 `_`로 씁니다(`naver-a`는 `MAIL_NAVER_A_ADDRESS`). `MAIL_ACCOUNTS`가 있으면 `MAIL_ADDRESS`, `MAIL_PASSWORD`, `MAIL_FULL_NAME`은 읽지 않습니다. 같은 서비스의 계정이 둘이어도 됩니다.

```json
{
  "mcpServers": {
    "mail": {
      "command": "/absolute/path/to/uvx",
      "args": ["--from", "git+https://github.com/M1nu0x0/korean-mail-mcp", "korean-mail-mcp"],
      "env": {
        "MAIL_ACCOUNTS": "naver-a,naver-b,daum",
        "MAIL_NAVER_A_ADDRESS": "a_id@naver.com",
        "MAIL_NAVER_A_PASSWORD": "your_app_password",
        "MAIL_NAVER_B_ADDRESS": "b_id@naver.com",
        "MAIL_NAVER_B_PASSWORD": "your_app_password",
        "MAIL_DAUM_ADDRESS": "your_id@daum.net",
        "MAIL_DAUM_PASSWORD": "your_imap_password"
      }
    }
  }
}
```

모든 도구가 선택 인자 `account`(계정 이름, 대소문자 구분 없음)를 받습니다. 계정이 여러 개일 때 `account`를 생략하면 이렇게 동작합니다.

| 도구 | `account`를 생략하면 |
|------|------|
| `get_profile`, `search_emails`, `list_folders`, `list_drafts` | 모든 계정에서 실행하고 `[{"account", "address", "result"}]`로 계정별로 묶어 돌려줍니다. 계정들은 나란히 실행되고, 실패한 계정은 `result` 대신 `error`를 담을 뿐 나머지는 계속됩니다 |
| `read_email`, `read_thread`, `download_attachment`, `create_draft`, `send_email`, `create_folder`, `move_emails`, `mark_read`, `trash_emails` | 오류. 어느 계정인지 `account`로 지정해야 합니다 |

- 쓰기 도구에 기본 계정이 없는 것은 메일이 뜻하지 않은 계정에서 나가거나 지워지지 않게 하려는 것입니다.
- 계정이 여러 개일 때 `account`를 주면 결과가 어느 계정의 것인지 알 수 있습니다. 객체 결과에는 `"account"` 필드가 붙고, 리스트 결과(`list_folders`, `list_drafts`, `read_thread`)는 `{"account": ..., "result": [...]}`로 감쌉니다.
- UID와 폴더는 계정마다 따로이므로, `search_emails` 결과의 UID는 그 결과가 속한 계정과 함께 써야 합니다.
- 전 계정 검색에서 `folder`, `page`, `page_size`는 계정마다 따로 적용됩니다. 계정들이 나란히 실행되므로 가장 느린 계정만큼 걸리고, 네이버는 헤더 조회가 느려서 보통 그 계정이 됩니다.
- 계정이 하나뿐이면 `MAIL_ACCOUNTS` 없이 지금까지처럼 쓰면 됩니다. `account`는 생략할 수 있고 결과에도 `account` 필드가 붙지 않습니다.
- 이름 뒤에 `?`를 붙이면(`MAIL_ACCOUNTS=naver?,daum?`) 선택 계정입니다. 주소가 비어 있으면 비밀번호가 남아 있어도 그 계정을 건너뜁니다. 주소만 있고 비밀번호가 없으면 오류이고, 건너뛴 뒤 계정이 하나도 남지 않아도 오류입니다.
- 플러그인은 서비스마다 계정 하나씩(네이버·다음·카카오)을 `MAIL_ACCOUNTS=naver?,daum?,kakao?`로 넘깁니다. 같은 서비스의 계정이 둘 이상이면 위처럼 서버를 직접 등록하세요.

## Tools Reference

모든 도구는 선택 인자 `account`를 받습니다. 여러 계정을 쓸 때만 필요하고, 규칙은 [Multiple Accounts](#multiple-accounts)에 있으며 아래 표에는 적지 않았습니다.

### get_profile
계정 프로필 조회. 파라미터 없음.

### search_emails
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| folder | string | No | INBOX | 검색할 폴더 |
| sender | string | No | - | 발신자 필터 |
| recipient | string | No | - | 수신자 필터 |
| subject | string | No | - | 제목 키워드 |
| date_from | string | No | - | 시작 날짜 (DD-Mon-YYYY) |
| date_to | string | No | - | 종료 날짜 (DD-Mon-YYYY) |
| is_read | boolean | No | - | 읽음 여부 (true/false/null) |
| page | integer | No | 1 | 페이지 번호 |
| page_size | integer | No | 20 | 페이지당 결과 수 (최대 100) |
| text_search | string | No | auto | 발신자·수신자·제목을 대조하는 방식: `auto`, `server`, `local` |

`text_search`에 따른 동작(2026-11-16 실제 계정 측정):

| 방식 | 네이버 | 다음·카카오 |
|------|--------|-------------|
| `local` | 정확, 대소문자 무시. 폴더의 메일 한 통당 약 50ms (411통에 약 20초) | 정확, 대소문자 무시. 2–5초 |
| `server` | 0.1–2초. 대소문자 무시, 최신 1,000건까지만 반환 | 근사치(98건 중 95건), 2–5초 |
| `auto` | `server` | `local` |

- `local`은 헤더를 받아 디코딩한 텍스트끼리 비교합니다.
- 네이버 서버는 대소문자를 구분하므로, `server`는 검색어의 모든 대소문자 조합을 OR로 묶어 보냅니다. 영문자가 7자를 넘으면 7자 단위로 나눠 후보를 좁힌 뒤 그 후보만 헤더를 받아 확인합니다. 확인은 후보 한 통당 약 50ms라서 후보가 1,000건이면 약 50초가 걸리고, 최신 1,000건 상한 때문에 후보가 잘리면 실제 일치 건이 빠질 수 있습니다. 발신자·수신자·제목에 모두 긴 검색어를 넣으면 서버에 보내는 조각 수가 줄어듭니다(OR 항 합계 1,024개 이하).
- 다음·카카오 서버는 디코딩하지 않은 헤더 원문과 대조합니다. 그래서 `server`는 한글의 base64·quoted-printable 형태를 찾고, 단어가 인코딩 조각 경계에 걸리면 놓칩니다.
- 다음은 방식과 무관하게 폴더마다 최근 400통만 보입니다.

### read_email
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uid | string | Yes | - | 메일 고유 ID |
| folder | string | No | INBOX | 폴더 |

### read_thread
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| message_id | string | Yes | - | Message-ID 헤더 값 |
| folder | string | No | INBOX | 폴더 |

### list_folders
폴더 목록 조회. 파라미터 없음.

### create_draft
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| to | array | Yes | - | 수신자 목록 |
| subject | string | Yes | - | 제목 |
| body | string | Yes | - | 본문 |
| body_type | string | No | text/plain | text/plain 또는 text/html |
| cc | array | No | - | 참조 목록 |

### list_drafts
초안 목록 조회. 파라미터 없음.

### send_email
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| to | array | Yes | - | 수신자 목록 |
| subject | string | Yes | - | 제목 |
| body | string | Yes | - | 본문 |
| body_type | string | No | text/plain | text/plain 또는 text/html |
| cc | array | No | - | 참조 목록 |
| in_reply_to | string | No | - | 답장 대상 Message-ID |
| references | array | No | - | 스레드 Message-ID 목록 |

### download_attachment
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uid | string | Yes | - | 메일 고유 ID |
| part_number | string | Yes | - | MIME 파트 번호 (read_email에서 확인) |
| folder | string | No | INBOX | 폴더 |

### create_folder
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| name | string | Yes | - | 폴더 이름 |

### move_emails
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uids | array | Yes | - | 옮길 메일의 UID 목록 (최대 500) |
| destination | string | Yes | - | 대상 폴더 이름 또는 `list_folders`의 `raw_name` |
| folder | string | No | INBOX | 메일이 지금 있는 폴더 |

이동한 뒤에는 UID가 바뀔 수 있으므로 대상 폴더에서 다시 검색해 확인합니다. 네이버·다음·카카오에서는 실측상 그대로 유지됐습니다.

응답은 서버가 이동 요청을 받았다는 뜻입니다. 서버는 없는 UID에도 OK로 답하므로 실제로 옮긴 개수는 알려 주지 않습니다. 대상 폴더를 검색해 확인하세요. 다음은 폴더마다 최근 400통만 보이므로 그보다 오래된 메일은 UID로 옮길 수 없습니다.

### mark_read
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uids | array | Yes | - | 메일 UID 목록 (최대 500) |
| folder | string | No | INBOX | 폴더 |
| read | boolean | No | true | true는 읽음, false는 안읽음 |

### trash_emails
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| uids | array | Yes | - | 메일 UID 목록 (최대 500) |
| folder | string | No | INBOX | 폴더 |

### 폴더 이름

`folder`와 `destination`에는 한글 이름(`영수증`)이나 `list_folders`가 돌려주는 `raw_name`을 쓸 수 있습니다.

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
cd site && npm ci && npm run build   # 사이트 빌드와 검사(site/dist)
cd site && npm run dev               # 로컬 미리보기
cd site && npm run og                # 언어별 링크 미리보기 이미지 생성(Playwright 필요)
```

`uv run pytest`에는 `tests/test_plugin.py`가 들어 있어서, 마켓플레이스와 `plugin.json`, `.mcp.json`, `pyproject.toml`, `server.py`가 서로 어긋나면(버전, 환경변수 이름, 필수 항목) 실패합니다.

사이트는 [Astro](https://astro.build)와 공용 키트 [claude-plugin-site](https://github.com/M1nu0x0/claude-plugin-site)로 만듭니다. 문구는 모두 `site/src/site.json`에, 섹션 순서는 `site/src/pages/[...lang].astro`에 있습니다. `npm run build`는 언어별 페이지(`/`, `/ko/`, `/ja/`)와 `sitemap.xml`을 만든 뒤 크롤러가 읽는 그대로 검사하고, 하나라도 어긋나면 실패합니다. main에 병합되면 Pages 워크플로가 빌드해 배포합니다(레포 설정의 Pages 소스는 **GitHub Actions**여야 합니다). 내용이 바뀌면 `site/src/site.json`의 `updated`도 그날 날짜로 바꿉니다. 바꾸지 않으면 PR에서 CI가 경고합니다. `ask`, `answer`, `ogImageLine`, `ogImageText`를 바꾸면 `npm run og`로 `site/public/images/og*.png`도 다시 만들어 커밋합니다.

새 버전은 `pyproject.toml`과 `plugins/korean-mail-mcp/.claude-plugin/plugin.json`의 `version`을 같이 올리는 PR을 병합한 뒤, 같은 버전으로 `vX.Y.Z` Release를 만듭니다. 태그가 생기면 CI가 태그와 두 `version`이 같은지 확인합니다. 플러그인의 `.mcp.json`은 서버를 버전에 고정하지 않고 이 저장소의 기본 브랜치에서 가져옵니다.

## 구성

```
.claude-plugin/
  marketplace.json      이 레포를 마켓플레이스로 등록
plugins/korean-mail-mcp/
  .claude-plugin/
    plugin.json         플러그인 매니페스트, userConfig 일곱 개
  .mcp.json             uvx로 서버를 띄우는 MCP 서버 정의
src/korean_mail_mcp/    MCP 서버(Python)
tests/                  단위 테스트(test_unit.py, test_plugin.py)와 통합 테스트
site/                   GitHub Pages 사이트(Astro): src/site.json 번역, src/pages/ 페이지
README.en.md, README.ja.md  README 번역본
```

플러그인은 `plugins/korean-mail-mcp/`에 따로 두고 마켓플레이스가 상대경로로 가리킵니다. claude.ai의 Add marketplace는 레포 루트를 통째로 플러그인으로 쓰는 구성을 받아주지 않는 경우가 있어서입니다.

## Troubleshooting

| Error | Solution |
|-------|----------|
| `IMAP authentication failed` | 앱 비밀번호 확인. 계정 비밀번호가 아닌 애플리케이션 비밀번호 사용 |
| `Cannot connect to IMAP server` | 네트워크 확인, IMAP 사용 설정 확인 |
| `Missing required environment variables` | `MAIL_ADDRESS`, `MAIL_PASSWORD` 환경변수 설정(여러 계정이면 오류가 알려 주는 `MAIL_<이름>_*`) |
| `account is required because more than one account is configured` | 계정이 여러 개일 때 이 도구는 `account`로 계정 이름을 지정해야 함 |
| `Unknown account` | 오류 메시지가 알려 주는 이름 중 하나를 `account`에 사용 |
| `Unsupported mail domain` | 지원 도메인(`naver.com`, `daum.net`, `hanmail.net`, `kakao.com`)의 주소인지 확인 |
| `Folder not found` | `list_folders` 도구로 사용 가능한 폴더명 확인 |
| `Failed to spawn process` | `command`에 `uvx`의 절대 경로 사용 (`which uvx`로 확인) |
| 플러그인을 켰는데 도구가 안 보임 | 새 세션에서 확인하고, `claude plugin list`로 켜져 있는지 확인 |
| 플러그인을 켰는데 서버가 시작하지 않음 (`No account in MAIL_ACCOUNTS`, `Missing required environment variables for account`) | Claude Code에서 `/plugin configure korean-mail-mcp@korean-mail-mcp`를 실행해 쓰는 서비스의 주소와 비밀번호를 둘 다 채움 |

## Technical Details

- **IMAP**: 포트 993 (SSL/TLS)
- **SMTP**: 포트 465 (SSL)
- **Transport**: stdio (Claude Desktop 연동)
- **Encoding**: UTF-8, EUC-KR, Modified UTF-7 (폴더명) 자동 처리
- **Connection**: 각 도구 호출마다 새 연결 (stateless)
- **Attachment limit**: 10MB (base64 인코딩)
- **Prompt injection**: 메일의 제목, 발신자, 본문, 첨부 이름은 제3자가 쓴 글입니다. 서버 지침, 도구 설명, 읽기 결과의 `security_notice` 필드가 모델에게 이를 데이터로만 다루라고 알립니다. 문구는 보조 수단이므로 `send_email`, `trash_emails`, `move_emails`, `download_attachment`는 호출 전에 사용자가 승인하도록 설정하는 것을 권장합니다.

## License

MIT
