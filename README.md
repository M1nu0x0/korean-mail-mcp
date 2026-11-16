# korean-mail-mcp

네이버·다음·카카오 메일을 MCP 클라이언트에서 쓰게 해 주는 MCP(Model Context Protocol) 서버입니다.
[chanmuzi/naver-mail-mcp](https://github.com/chanmuzi/naver-mail-mcp)의 fork이며, 다음·카카오 지원과 메일함 정리 도구를 더했습니다.

서버 프로세스 하나가 계정 하나를 맡고, 접속할 서버는 이메일 주소의 도메인으로 정합니다.

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

## Installation

PyPI에는 배포되어 있지 않습니다. `uvx`로 이 저장소에서 바로 실행합니다.

```bash
uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp
```

## MCP Client Configuration

계정마다 서버를 하나씩 등록합니다.

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

> **주의:** Claude Desktop은 시스템 PATH를 상속하지 않습니다. `command`에는 `uvx`의 **절대 경로**를 쓰세요. `which uvx`로 확인할 수 있습니다.

## Prerequisites

1. **Python 3.10+**
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

## Tools Reference

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

이동하면 UID가 바뀝니다.

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

`folder`와 `destination`에는 한글 이름(`영수증`)이나 `list_folders`가 돌려주는 `raw_name`을 쓸 수 있습니다. 이름에 `&`가 들어 있으면 `raw_name`을 쓰세요.

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
```

## Troubleshooting

| Error | Solution |
|-------|----------|
| `IMAP authentication failed` | 앱 비밀번호 확인. 계정 비밀번호가 아닌 애플리케이션 비밀번호 사용 |
| `Cannot connect to IMAP server` | 네트워크 확인, IMAP 사용 설정 확인 |
| `Missing required environment variables` | `MAIL_ADDRESS`, `MAIL_PASSWORD` 환경변수 설정 |
| `Unsupported mail domain` | 지원 도메인(`naver.com`, `daum.net`, `hanmail.net`, `kakao.com`)의 주소인지 확인 |
| `Folder not found` | `list_folders` 도구로 사용 가능한 폴더명 확인 |
| `Failed to spawn process` | `command`에 `uvx`의 절대 경로 사용 (`which uvx`로 확인) |

## Technical Details

- **IMAP**: 포트 993 (SSL/TLS)
- **SMTP**: 포트 465 (SSL)
- **Transport**: stdio (Claude Desktop 연동)
- **Encoding**: UTF-8, EUC-KR, Modified UTF-7 (폴더명) 자동 처리
- **Connection**: 각 도구 호출마다 새 연결 (stateless)
- **Attachment limit**: 10MB (base64 인코딩)

## License

MIT
