# korean-mail-mcp

[![release](https://img.shields.io/github/v/release/M1nu0x0/korean-mail-mcp)](https://github.com/M1nu0x0/korean-mail-mcp/releases)
[![CI](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/ci.yml)
[![Plugin](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/plugin.yml/badge.svg)](https://github.com/M1nu0x0/korean-mail-mcp/actions/workflows/plugin.yml)
[![license](https://img.shields.io/github/license/M1nu0x0/korean-mail-mcp)](LICENSE)

[한국어](README.md) | [English](README.en.md) | **日本語**

Naver、Daum、Kakao のメールを Claude から使えるようにする Claude Code プラグイン兼 MCP(Model Context Protocol)サーバーです。
[chanmuzi/naver-mail-mcp](https://github.com/chanmuzi/naver-mail-mcp) の fork で、Daum と Kakao への対応と、メールボックスを整理するツールを加えています。

サーバープロセス 1 つは既定で 1 アカウントを担当し(`MAIL_ACCOUNTS` で複数のアカウントを任せることもできます)、接続先のサーバーはメールアドレスのドメインで決まります。

**[Website](https://m1nu0x0.github.io/korean-mail-mcp/ja/) · [Releases](https://github.com/M1nu0x0/korean-mail-mcp/releases) · [Changelog](CHANGELOG.md)**

| ドメイン | IMAP | SMTP |
|----------|------|------|
| `naver.com` | `imap.naver.com` | `smtp.naver.com` |
| `daum.net`、`hanmail.net` | `imap.daum.net` | `smtp.daum.net` |
| `kakao.com` | `imap.kakao.com` | `smtp.kakao.com` |

## Features

| ツール | 説明 |
|--------|------|
| `get_profile` | アカウントのプロフィール(アドレス、名前、メールの総数、未読数) |
| `search_emails` | 差出人、宛先、件名、日付、既読状態で検索。ページ送りあり |
| `read_email` | UID でメール全体を読む(ヘッダー、本文、添付ファイルのメタ情報) |
| `read_thread` | Message-ID でスレッドを読む |
| `list_folders` | フォルダの一覧(メール数、未読数つき) |
| `create_draft` | 新しい下書きを下書きフォルダに保存 |
| `list_drafts` | 下書きフォルダの下書き一覧 |
| `send_email` | SMTP でメールを送信(新規メール、返信) |
| `download_attachment` | 添付ファイルをダウンロード(base64 エンコード) |
| `create_folder` | フォルダ(マイメールボックス)を作成 |
| `move_emails` | メールを別のフォルダへ移動 |
| `mark_read` | 既読 / 未読にする |
| `trash_emails` | ごみ箱へ移動(完全には削除しない) |

これらのサービスには Gmail のようなラベルがありません。メール 1 通は 1 つのフォルダにだけ入るので、整理はフォルダを作ってそこへ移す形で行います。

## Installation

### Claude Code プラグイン

Claude Code のターミナルのプロンプトで:

```
/plugin install korean-mail-mcp --marketplace M1nu0x0/korean-mail-mcp
```

`Add marketplace?` に `y` と答え、scope は user を選びます。シェルからは次のようにインストールします。

```sh
claude plugin install korean-mail-mcp --marketplace M1nu0x0/korean-mail-mcp
```

Claude Desktop では、プロンプト横の `+` → Plugins → Add marketplace に `M1nu0x0/korean-mail-mcp` を入力し、`korean-mail-mcp` を追加します。次のセッションから適用されます。

`uvx` が `PATH` にあるよう、[uv](https://docs.astral.sh/uv/) をインストールしておいてください。サーバーはこのリポジトリから `uvx` で直接実行され(PyPI には公開していません)、ほかにインストールするものはありません。

プラグインを有効にすると、Claude Code が 7 つの値を尋ねます。使うサービスだけ入力し、残りは空のままにします。サーバー 1 つがサービスごとに 1 アカウント、最大 3 つのアカウントを担当します。

| 項目 | 必須 | 説明 |
|------|------|------|
| Naver address (`naver_address`) | No | Naver のメールアドレス全体。Naver を使わないなら空 |
| Naver IMAP password (`naver_password`) | No | Naver のアプリケーションパスワード(アカウントのパスワードではない)。`settings.json` ではなく機密値として別に保管される |
| Daum address (`daum_address`) | No | Daum のメールアドレス全体(`daum.net` または `hanmail.net`)。Daum を使わないなら空 |
| Daum IMAP password (`daum_password`) | No | Daum の IMAP 用パスワード(アカウントのパスワードではない)。機密値として別に保管される |
| Kakao address (`kakao_address`) | No | Kakao のメールアドレス全体。Kakao を使わないなら空 |
| Kakao IMAP password (`kakao_password`) | No | Kakao の IMAP 用パスワード(アカウントのパスワードではない)。機密値として別に保管される |
| Display name (`mail_full_name`) | No | 送信メールに表示する名前。すべてのアカウントに共通で、空ならアドレスだけを使う |

IMAP 用のパスワードの入手方法は、下の [Prerequisites](#prerequisites) にあります。サービスごとにアドレスとパスワードの両方を入力します。アドレスだけでパスワードがないとサーバーは起動せず、アドレスが空のサービスはパスワードが残っていても飛ばされます。すべてのサービスが空でもサーバーは起動しません。あとで変えるには、Claude Code で `/plugin configure korean-mail-mcp@korean-mail-mcp` を実行します。

アカウントが 1 つなら、これまでどおりに動きます。複数のときは、[Multiple Accounts](#multiple-accounts) のとおり `account` 引数でどのアカウント(`naver`、`daum`、`kakao`)かを指定します。同じサービスのアカウントが 2 つ以上ある場合や、Claude Code 以外の MCP クライアントで使う場合は、下の [MCP Client Configuration](#mcp-client-configuration) のようにサーバーを手動で登録します。

無効にするには `claude plugin disable korean-mail-mcp`、削除するには `claude plugin uninstall korean-mail-mcp` を実行します。

### uvx で直接実行

```bash
uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp
```

## MCP Client Configuration

プラグインを使わない場合です。アカウントごとにサーバーを 1 つずつ登録します。

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

Claude Code では、同じサーバーを `claude mcp add` で登録できます。サーバー名はアカウントごとに別にする必要があり(同じ名前を再び使うと `already exists` エラーになります)、サービスは名前ではなくアドレスのドメインで決まります。同じサービスのアカウントが 2 つなら、`naver-mail-a`、`naver-mail-b` のように名前を分けてください。

```bash
claude mcp add --scope user naver-mail-a -e MAIL_ADDRESS=a_id@naver.com -e MAIL_PASSWORD=your_app_password -- uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp
claude mcp add --scope user naver-mail-b -e MAIL_ADDRESS=b_id@naver.com -e MAIL_PASSWORD=your_app_password -- uvx --from git+https://github.com/M1nu0x0/korean-mail-mcp korean-mail-mcp
```

ツールもサーバーごとに分かれて表示されるので、どのアカウントかは `get_profile` で確認します。この方法では、入力した値はプラグインの機密値のように別保管されず、`~/.claude.json` にそのまま保存されます。手動で登録したサーバーだけを使う場合は、プラグインを `claude plugin disable korean-mail-mcp` で無効にします。

> **注意:** Claude Desktop はシステムの PATH を引き継ぎません。`command` には `uvx` の**絶対パス**を書いてください。`which uvx` で確認できます。プラグインの `.mcp.json` は `uvx` を名前で呼ぶので、同じ理由でサーバーが起動しない場合は、この方法で手動登録してください。

## Prerequisites

1. **Python 3.10+**(`uvx` が自動で用意します)
2. メールサービスで **IMAP/SMTP を有効**にする
   - Naver: メール → 設定 → POP3/IMAP 設定 → IMAP/SMTP を使用
   - Daum と Kakao: メール → 設定 → IMAP/POP3 → IMAP を使用
3. **IMAP 用のパスワード**を用意する(ログインパスワードではありません)
   - Naver: マイ情報 → セキュリティ設定 → 2 段階認証 → アプリケーションパスワードの管理
   - Daum と Kakao: IMAP 設定画面に表示される専用パスワード

## Environment Variables

| 変数 | 必須 | 説明 |
|------|------|------|
| `MAIL_ADDRESS` | Yes | メールアドレス。ドメインでサービスが決まる |
| `MAIL_PASSWORD` | Yes | IMAP 用のパスワード(アカウントのパスワードではない) |
| `MAIL_FULL_NAME` | No | 送信メールの表示名 |
| `MAIL_ACCOUNTS` | No | 複数のアカウントの名前の一覧。あると上の 3 つの代わりに `MAIL_<名前>_*` を読む。[Multiple Accounts](#multiple-accounts) 参照 |

プラグインは `MAIL_ACCOUNTS=naver?,daum?,kakao?` と、サービスごとの `MAIL_NAVER_*`、`MAIL_DAUM_*`、`MAIL_KAKAO_*` をサーバーに渡します。`mail_full_name` は 3 アカウントの `MAIL_<名前>_FULL_NAME` に同じ値で入ります。

## Multiple Accounts

1 つのサーバーで複数のアカウントを扱うには、`MAIL_ACCOUNTS` にアカウント名をカンマ区切りで並べ、名前ごとに `MAIL_<名前>_ADDRESS`、`MAIL_<名前>_PASSWORD`、`MAIL_<名前>_FULL_NAME`(任意)を渡します。名前は英字で始まり、英字、数字、`-`、`_` を使えて、32 文字までです。変数名では名前を大文字にし、`-` を `_` と書きます(`naver-a` は `MAIL_NAVER_A_ADDRESS`)。`MAIL_ACCOUNTS` があると、`MAIL_ADDRESS`、`MAIL_PASSWORD`、`MAIL_FULL_NAME` は読みません。同じサービスのアカウントが 2 つでも構いません。

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

すべてのツールが任意の引数 `account`(アカウント名、大文字小文字は区別しない)を受け取ります。アカウントが複数のとき、`account` を省略すると次のように動きます。

| ツール | `account` を省略すると |
|------|------|
| `get_profile`、`search_emails`、`list_folders`、`list_drafts` | すべてのアカウントで実行し、`[{"account", "address", "result"}]` としてアカウントごとにまとめて返します。アカウントは並行して実行され、失敗したアカウントは `result` の代わりに `error` を持つだけで、残りは続行されます |
| `read_email`、`read_thread`、`download_attachment`、`create_draft`、`send_email`、`create_folder`、`move_emails`、`mark_read`、`trash_emails` | エラー。どのアカウントかを `account` で指定する必要があります |

- メールを送る、変更するツールに既定のアカウントがないのは、意図しないアカウントからメールが出たり、削除されたりしないようにするためです。
- アカウントが複数のとき `account` を渡すと、結果がどのアカウントのものか分かります。オブジェクトの結果には `"account"` フィールドが付き、リストの結果(`list_folders`、`list_drafts`、`read_thread`)は `{"account": ..., "result": [...]}` の形で包まれます。
- UID とフォルダーはアカウントごとに別なので、`search_emails` の結果の UID は、その結果が属するアカウントと一緒に使います。
- 全アカウントの検索では、`folder`、`page`、`page_size` はアカウントごとに別に適用されます。アカウントは並行して実行されるので、最も遅いアカウント分の時間がかかり、Naver はヘッダー取得が遅いため、たいていそれになります。
- アカウントが 1 つだけなら、`MAIL_ACCOUNTS` なしでこれまでどおり使えます。`account` は省略でき、結果に `account` フィールドは付きません。
- 名前の後ろに `?` を付けると(`MAIL_ACCOUNTS=naver?,daum?`)任意のアカウントになります。アドレスが空なら、パスワードが残っていてもそのアカウントは飛ばされます。アドレスだけでパスワードがないとエラーで、飛ばした結果アカウントが 1 つも残らない場合もエラーです。
- プラグインは、サービスごとに 1 アカウントずつ(Naver、Daum、Kakao)を `MAIL_ACCOUNTS=naver?,daum?,kakao?` として渡します。同じサービスのアカウントが 2 つ以上なら、上のようにサーバーを手動で登録してください。

## Tools Reference

すべてのツールが任意の引数 `account` を受け取ります。複数のアカウントを使うときだけ必要で、規則は [Multiple Accounts](#multiple-accounts) にあり、下の表には載せていません。

### get_profile
アカウントのプロフィールを取得します。パラメーターはありません。

### search_emails
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| folder | string | No | INBOX | 検索するフォルダ |
| sender | string | No | - | 差出人のフィルター |
| recipient | string | No | - | 宛先のフィルター |
| subject | string | No | - | 件名のキーワード |
| date_from | string | No | - | 開始日(DD-Mon-YYYY) |
| date_to | string | No | - | 終了日(DD-Mon-YYYY) |
| is_read | boolean | No | - | 既読状態(true/false/null) |
| page | integer | No | 1 | ページ番号 |
| page_size | integer | No | 20 | 1 ページの件数(最大 100) |
| text_search | string | No | auto | 差出人、宛先、件名の照合方法: `auto`、`server`、`local` |

`text_search` の動作(2026-11-16 に実際のアカウントで測定):

| 方式 | Naver | Daum と Kakao |
|------|-------|---------------|
| `local` | 正確、大文字小文字を区別しない。フォルダ内のメール 1 通あたり約 50ms(411 通で約 20 秒) | 正確、大文字小文字を区別しない。2〜5 秒 |
| `server` | 0.1〜2 秒。大文字小文字を区別せず、新しい 1,000 件までしか返さない | 近似(98 件中 95 件)、2〜5 秒 |
| `auto` | `server` | `local` |

- `local` はヘッダーをダウンロードし、デコードしたテキスト同士を比べます。
- Naver のサーバーは大文字小文字を区別するため、`server` は検索語の大文字小文字の組み合わせをすべて OR でつないで送ります。英字が 7 文字を超える場合は 7 文字ずつに分けて候補を絞り、その候補だけヘッダーをダウンロードして確認します。確認は候補 1 通あたり約 50ms なので、候補が 1,000 件なら約 50 秒かかり、新しい 1,000 件の上限で候補が切れると、実際に一致するメールが漏れることがあります。差出人、宛先、件名のすべてに長い検索語を入れると、サーバーに送る断片の数が減ります(OR の項は合計 1,024 個以下)。
- Daum と Kakao のサーバーは、デコードしていないヘッダーの生のデータと照合します。そのため `server` は韓国語の base64 や quoted-printable の形を探し、単語がエンコードされた断片の境目にかかると見逃します。
- Daum は、どの方式でもフォルダごとに新しい 400 通しか見えません。

### read_email
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| uid | string | Yes | - | メールの固有 ID |
| folder | string | No | INBOX | フォルダ |
| max_chars | integer | No | - | `body_text` と `body_html` をそれぞれこの文字数(1 以上)までだけ返します。省略すると全文です。返す量を減らすだけで、メールは全部ダウンロードします |

結果には、送信者を確かめるためのヘッダー由来の情報が含まれます。

| フィールド | 意味 |
|------------|------|
| `reply_to` | `Reply-To` のアドレス一覧。ヘッダーがなければ空のリスト |
| `reply_to_differs` | `Reply-To` に、`From` のアドレスと無関係なドメインのものがあれば `true`。同じドメイン、または一方がもう一方のサブドメインなら無関係とは見なしません |
| `list_unsubscribe` | `List-Unsubscribe` ヘッダーがあれば `true`。一斉送信メールの目印です |
| `authentication` | メールサービスが記録した `spf`、`dkim`、`dmarc` の結果(`pass`、`fail`、`softfail`、`neutral`、`none`、`policy`、`temperror`、`permerror`)。記録がない項目は含まれません |
| `truncated` | `max_chars` で本文が切られたら `true` |

- Naver は `Authentication-Results` に 3 つとも記録します。Daum と Kakao は `Received-SPF` だけを記録するので `spf` のみになります。2026-11-18 に 3 つのアカウントの受信トレイの最新メール(Naver と Daum は 80 通、Kakao は 56 通)で確認したところ、ほぼすべて `pass` でした。
- メールサービス自身の名前(`mx.naver.com`、`mx.daum.net`、`kakao.com`)が入った行だけを読み、同じ種類の行のうち一番上(最新)の 1 本だけを見ます。送信者や中継サービスが入れた行は無視します。Daum の 1 通は、中継した SparkPost サーバーの `Authentication-Results` だけを持っていました。
- ヘッダーに書かれた値なので送信者が偽装でき、`pass` は送信者が名乗り通りの人であることの証明ではありません。メールをより詳しく調べる手がかりとして使い、安全だと判断する根拠にはしないでください。

### read_thread
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| message_id | string | Yes | - | Message-ID ヘッダーの値 |
| folder | string | No | INBOX | フォルダ |
| max_chars | integer | No | - | スレッドのすべてのメールに `read_email` と同じように適用します |

スレッドの各メールにも `read_email` と同じフィールドが含まれます。

### list_folders
フォルダの一覧を取得します。パラメーターはありません。

### create_draft
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| to | array | Yes | - | 宛先の一覧 |
| subject | string | Yes | - | 件名 |
| body | string | Yes | - | 本文 |
| body_type | string | No | text/plain | text/plain または text/html |
| cc | array | No | - | Cc の一覧 |

### list_drafts
下書きの一覧を取得します。パラメーターはありません。

### send_email
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| to | array | Yes | - | 宛先の一覧 |
| subject | string | Yes | - | 件名 |
| body | string | Yes | - | 本文 |
| body_type | string | No | text/plain | text/plain または text/html |
| cc | array | No | - | Cc の一覧 |
| in_reply_to | string | No | - | 返信先の Message-ID |
| references | array | No | - | スレッドの Message-ID の一覧 |

### download_attachment
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| uid | string | Yes | - | メールの固有 ID |
| part_number | string | Yes | - | MIME パートの番号(read_email で確認) |
| folder | string | No | INBOX | フォルダ |

### create_folder
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| name | string | Yes | - | フォルダ名 |

### move_emails
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| uids | array | Yes | - | 移すメールの UID の一覧(最大 500) |
| destination | string | Yes | - | 移動先のフォルダ名、または `list_folders` の `raw_name` |
| folder | string | No | INBOX | メールが今あるフォルダ |

移動したあとは UID が変わることがあるので、移動先のフォルダで検索し直して確認します。Naver、Daum、Kakao では、実測では変わりませんでした。

応答は、サーバーが移動の要求を受け取ったという意味です。サーバーは存在しない UID にも OK と答えるので、実際に移した件数は分かりません。移動先のフォルダを検索して確認してください。Daum はフォルダごとに新しい 400 通しか見えないため、それより古いメールは UID で移せません。

### mark_read
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| uids | array | Yes | - | メールの UID の一覧(最大 500) |
| folder | string | No | INBOX | フォルダ |
| read | boolean | No | true | true で既読、false で未読 |

### trash_emails
| パラメーター | 型 | 必須 | 既定値 | 説明 |
|--------------|----|------|--------|------|
| uids | array | Yes | - | メールの UID の一覧(最大 500) |
| folder | string | No | INBOX | フォルダ |

### フォルダ名

`folder` と `destination` には、韓国語の名前(`영수증`)や、`list_folders` が返す `raw_name` を使えます。

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
cd site && npm ci && npm run build   # サイトのビルドと検査(site/dist)
cd site && npm run dev               # ローカルプレビュー
cd site && npm run og                # 言語ごとのリンクプレビュー画像を生成(Playwright が必要)
```

`uv run pytest` には `tests/test_plugin.py` が含まれていて、マーケットプレイス、`plugin.json`、`.mcp.json`、`pyproject.toml`、`server.py` が食い違うと(バージョン、環境変数の名前、必須の項目)失敗します。

サイトは [Astro](https://astro.build) と共通キット [claude-plugin-site](https://github.com/M1nu0x0/claude-plugin-site) で作ります。文言はすべて `site/src/site.json` に、セクションの順序は `site/src/pages/[...lang].astro` にあります。`npm run build` は言語ごとのページ(`/`、`/ko/`、`/ja/`)と `sitemap.xml` を作ったあと、クローラーが読むとおりに検査し、1 つでも外れると失敗します。main にマージされると Pages ワークフローがビルドしてデプロイします(リポジトリ設定の Pages のソースは **GitHub Actions** にします)。文言を変えたら `site/src/site.json` の `updated` もその日の日付にします。変えないと、プルリクエストで CI が警告します。`ask`、`answer`、`ogImageLine`、`ogImageText` を変えたら、`npm run og` で `site/public/images/og*.png` も作り直してコミットします。

新しいバージョンは、`pyproject.toml` と `plugins/korean-mail-mcp/.claude-plugin/plugin.json` の `version` を一緒に上げるプルリクエストをマージしたあと、同じバージョンで `vX.Y.Z` の Release を作ります。タグができると、CI がタグと 2 つの `version` が同じか確認します。プラグインの `.mcp.json` はサーバーをバージョンに固定せず、このリポジトリのデフォルトブランチから取得します。

## 構成

```
.claude-plugin/
  marketplace.json      このリポジトリをマーケットプレイスとして登録
plugins/korean-mail-mcp/
  .claude-plugin/
    plugin.json         プラグインのマニフェスト、userConfig 7 つ
  .mcp.json             uvx でサーバーを起動する MCP サーバーの定義
src/korean_mail_mcp/    MCP サーバー(Python)
tests/                  単体テスト(test_unit.py、test_plugin.py)と統合テスト
site/                   GitHub Pages のサイト(Astro): src/site.json に翻訳、src/pages/ にページ
README.en.md, README.ja.md  README の翻訳
```

プラグインは `plugins/korean-mail-mcp/` に分けて置き、マーケットプレイスが相対パスで指しています。claude.ai の Add marketplace は、リポジトリのルートをそのままプラグインにする構成を受け付けないことがあるためです。

## Troubleshooting

| エラー | 対処 |
|--------|------|
| `IMAP authentication failed` | アプリケーションパスワードを確認する。アカウントのパスワードではなくアプリケーションパスワードを使う |
| `Cannot connect to IMAP server` | ネットワークと、IMAP が有効になっているかを確認する |
| `Missing required environment variables` | `MAIL_ADDRESS` と `MAIL_PASSWORD` を設定する(複数のアカウントなら、エラーが示す `MAIL_<名前>_*`) |
| `account is required because more than one account is configured` | アカウントが複数のとき、このツールは `account` でどのアカウントかを指定する必要がある |
| `Unknown account` | エラーが示す名前のどれかを `account` に使う |
| `Unsupported mail domain` | 対応するドメイン(`naver.com`、`daum.net`、`hanmail.net`、`kakao.com`)のアドレスか確認する |
| `Folder not found` | `list_folders` ツールで使えるフォルダ名を確認する |
| `Failed to spawn process` | `command` に `uvx` の絶対パスを使う(`which uvx` で確認) |
| プラグインを有効にしてもツールが見えない | 新しいセッションで確認し、`claude plugin list` で有効になっているか確認する |
| プラグインを有効にしてもサーバーが起動しない(`No account in MAIL_ACCOUNTS`、`Missing required environment variables for account`) | Claude Code で `/plugin configure korean-mail-mcp@korean-mail-mcp` を実行し、使うサービスのアドレスとパスワードの両方を入力する |

## Technical Details

- **IMAP**: ポート 993(SSL/TLS)
- **SMTP**: ポート 465(SSL)
- **Transport**: stdio(Claude Desktop と Claude Code)
- **Encoding**: UTF-8、EUC-KR、Modified UTF-7(フォルダ名)を自動で処理
- **Connection**: ツールを呼ぶたびに新しい接続(ステートレス)
- **Attachment limit**: 10MB(base64 エンコード)
- **Prompt injection**: メールの件名、差出人、本文、添付ファイル名は第三者が書いたものです。サーバーの instructions、ツールの説明、読み取り結果の `security_notice` フィールドが、これらをデータとして扱うようモデルに伝えます。文言はあくまで補助なので、`send_email`、`trash_emails`、`move_emails`、`download_attachment` は実行前にユーザーの承認を求める設定を推奨します。

## License

MIT
