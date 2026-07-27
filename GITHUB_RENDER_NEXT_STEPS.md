# GitHubとRenderで外部公開する次の手順

このリポジトリは、すでに初期コミット済みです。

```text
ba61ce3 Prepare LIFE submission manager for Render MVP
```

## 1. GitHubで空のリポジトリを作る

GitHubで新しいリポジトリを作成します。

推奨名:

```text
life-submission-manager
```

作成時は、README、.gitignore、ライセンスを追加しないでください。
このフォルダにはすでに必要なファイルがあります。

## 2. このPCからGitHubへpushする

GitHubで表示されるリポジトリURLを使って、PowerShellで次を実行します。

```powershell
cd C:\Users\tanaka\Documents\Codex\2026-07-22\life-web-life-zip-sandbox-mnt\work\zip_extract_2\life_submission_manager
git branch -M main
git remote add origin https://github.com/<GitHubユーザー名>/life-submission-manager.git
git push -u origin main
```

`origin` がすでにあると言われた場合は、次で差し替えます。

```powershell
git remote set-url origin https://github.com/<GitHubユーザー名>/life-submission-manager.git
git push -u origin main
```

## 3. RenderでBlueprintとして読み込む

Renderで次を選びます。

```text
New -> Blueprint
```

GitHubの `life-submission-manager` リポジトリを選ぶと、Renderが `render.yaml` を読み込みます。

作成されるもの:

- Django Web Service
- PostgreSQL Database

## 4. Renderの環境変数を設定する

RenderのWeb Serviceで以下を設定します。

```text
DJANGO_ALLOWED_HOSTS=<Renderのホスト名>
DJANGO_CSRF_TRUSTED_ORIGINS=https://<Renderのホスト名>
```

例:

```text
DJANGO_ALLOWED_HOSTS=life-submission-manager.onrender.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://life-submission-manager.onrender.com
```

`localhost` や `127.0.0.1` は外部公開URLには使いません。

## 5. 初回データを入れる

RenderのShellで次を実行します。

```bash
python manage.py load_official_rules
python manage.py createsuperuser
```

デモ表示を入れる場合だけ、次も実行します。

```bash
python manage.py seed_demo_data
```

## 6. 公開前チェック

RenderのShellで次を実行します。

```bash
python manage.py check_deployment_readiness
```

画面では、管理ユーザーでログイン後に「公開前チェック」を開きます。

## このPCで未確認のこと

このPCでは以下が未導入だったため、ローカルからの実行確認はしていません。

- GitHub CLI `gh`
- Docker

ただし、RenderはGitHubリポジトリからDockerビルドするため、このPCにDockerが無くても公開作業は進められます。

