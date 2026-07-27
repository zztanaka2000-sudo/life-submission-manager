# LIFE提出管理アプリ

介護施設向けに、LIFE関連加算の提出予定、期限、提出状態、入力漏れ、LIFE登録人数との照合を管理するDjango製Webアプリです。

## 主な機能

- 科学的介護推進体制加算、個別機能訓練加算、ADL維持等加算の提出予定管理
- 翌月10日を基準にした提出期限計算
- 未提出、期限接近、期限超過、提出済みの状態管理
- LIFE登録人数とアプリ登録人数の照合
- 計画作成日、変更日、ADL基準日などの入力漏れ警告
- 入院、退院、利用再開時の再確認警告
- 法人、施設ごとのアクセス権限
- 操作監査ログ
- CSV出力、提出実績CSV取込
- 制度変更時に旧ルールを残したまま新版を追加できるルール履歴管理

## ローカル起動

PowerShellで実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py load_official_rules
.\.venv\Scripts\python manage.py seed_demo_data
.\.venv\Scripts\python manage.py runserver 127.0.0.1:8000
```

ブラウザで次を開きます。

```text
http://localhost:8000/
```

デモログイン:

```text
ユーザー名: demo_admin
パスワード: demo-pass-2026
```

## Docker起動

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py load_official_rules
```

## 外部公開

Render向けの `render.yaml` と `Dockerfile` を同梱しています。

詳しい手順は [RENDER_MVP_DEPLOY.md](./RENDER_MVP_DEPLOY.md) を確認してください。

外部公開時は、少なくとも以下を必ず設定します。

- `DJANGO_DEBUG=false`
- 強い `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- PostgreSQLの `DATABASE_URL`
- `SECURE_SSL_REDIRECT=true`
- `SESSION_COOKIE_SECURE=true`
- `CSRF_COOKIE_SECURE=true`

## 公開前チェック

```bash
python manage.py check_deployment_readiness
```

管理ユーザーでログイン後、画面上の「公開前チェック」からも確認できます。

## テスト

```bash
pytest
```

またはPowerShell:

```powershell
.\.venv\Scripts\python -m pytest
```

## 注意

このアプリはLIFEへの直接自動送信を行いません。現時点では、提出予定管理、照合、CSV出力までを対象にしています。

制度上の解釈、算定可否、自治体・保険者の運用差、最新通知への対応は、必ず制度担当者が確認してください。
