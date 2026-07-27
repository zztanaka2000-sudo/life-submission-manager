# Renderで外部PCから使えるMVPとして公開する手順

この手順は、ローカルDjango本体をRender上のWebサービスとして公開するための最短ルートです。

## 1. GitHubへ配置

この `life_submission_manager` フォルダをGitHubリポジトリへpushします。

公開前に以下がGitHubへ入らないことを確認してください。

- `.env`
- `db.sqlite3`
- `.venv/`
- `server.log`
- `server.err.log`

## 2. RenderでBlueprint作成

Renderで `New` → `Blueprint` を選び、このリポジトリを接続します。

Renderは `render.yaml` を読み、次を作成します。

- Web Service: `life-submission-manager`
- PostgreSQL: `life-manager-db`

MVP検証用として無料プランを指定しています。無料PostgreSQLは30日で期限切れになるため、継続運用する場合は有料プランへ変更してください。

無料MVPでは `AUTO_SEED_DEMO=true` により、起動時にデモ用ルール、施設、利用者、管理ユーザーを自動投入します。

## 3. 環境変数を設定

初回デプロイ後、RenderのWeb Serviceで以下を設定します。

```text
DJANGO_ALLOWED_HOSTS=<Renderのホスト名>
DJANGO_CSRF_TRUSTED_ORIGINS=https://<Renderのホスト名>
```

例:

```text
DJANGO_ALLOWED_HOSTS=life-submission-manager.onrender.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://life-submission-manager.onrender.com
```

`DJANGO_SECRET_KEY` と `DATABASE_URL` は `render.yaml` 側で自動作成されます。

## 4. 初期データを投入

本番運用ではRenderのShellから次を実行します。

```bash
python manage.py load_official_rules
python manage.py createsuperuser
```

デモデータを使わず本番運用する場合、`AUTO_SEED_DEMO=false` に変更し、管理画面から法人、施設、ユーザー、利用者、加算対象を登録してください。

## 5. 公開前チェック

RenderのShellで次を実行します。

```bash
python manage.py check_deployment_readiness
```

または、管理ユーザーでログインして `/deployment-check/` を確認します。

## 6. 外部PCでアクセス

RenderのURLを外部PCのブラウザで開きます。

```text
https://<Renderのホスト名>/
```

`localhost` や `127.0.0.1` はローカルPC専用です。外部PCには共有しません。
