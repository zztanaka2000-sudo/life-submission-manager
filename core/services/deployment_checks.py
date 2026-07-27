from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model

from core.models import RuleVersion, ValidationIssue


@dataclass(frozen=True)
class DeploymentCheck:
    code: str
    label: str
    status: str
    message: str


def _status(ok: bool, *, warning: bool = False) -> str:
    if ok:
        return "ok"
    return "warning" if warning else "error"


def run_deployment_checks():
    User = get_user_model()
    checks = [
        DeploymentCheck(
            "debug",
            "DEBUG設定",
            _status(not settings.DEBUG),
            "本番ではDJANGO_DEBUG=falseにしてください。" if settings.DEBUG else "DEBUGは無効です。",
        ),
        DeploymentCheck(
            "secret_key",
            "SECRET_KEY",
            _status(settings.SECRET_KEY != "unsafe-development-only"),
            "DJANGO_SECRET_KEYに長くランダムな値を設定してください。"
            if settings.SECRET_KEY == "unsafe-development-only"
            else "開発用の既定値ではありません。",
        ),
        DeploymentCheck(
            "allowed_hosts",
            "ALLOWED_HOSTS",
            _status(any(host not in {"localhost", "127.0.0.1"} for host in settings.ALLOWED_HOSTS), warning=True),
            "公開URLのホスト名をDJANGO_ALLOWED_HOSTSに設定してください。"
            if not any(host not in {"localhost", "127.0.0.1"} for host in settings.ALLOWED_HOSTS)
            else "公開用ホスト名が含まれています。",
        ),
        DeploymentCheck(
            "database",
            "データベース",
            _status(settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3", warning=True),
            "外部公開ではPostgreSQLを使用してください。"
            if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
            else "PostgreSQL等の外部DB設定です。",
        ),
        DeploymentCheck(
            "ssl_redirect",
            "HTTPS強制",
            _status(settings.SECURE_SSL_REDIRECT),
            "SECURE_SSL_REDIRECT=trueにしてください。" if not settings.SECURE_SSL_REDIRECT else "HTTPSリダイレクトが有効です。",
        ),
        DeploymentCheck(
            "secure_cookies",
            "Secure Cookie",
            _status(settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE),
            "SESSION_COOKIE_SECUREとCSRF_COOKIE_SECUREをtrueにしてください。"
            if not (settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE)
            else "Cookie保護が有効です。",
        ),
        DeploymentCheck(
            "hsts",
            "HSTS",
            _status(settings.SECURE_HSTS_SECONDS > 0),
            "本番ではHSTSを有効にしてください。" if settings.SECURE_HSTS_SECONDS <= 0 else "HSTSが有効です。",
        ),
        DeploymentCheck(
            "csrf_origins",
            "CSRF信頼済みURL",
            _status(any(origin.startswith("https://") for origin in settings.CSRF_TRUSTED_ORIGINS), warning=True),
            "公開URLをDJANGO_CSRF_TRUSTED_ORIGINSにhttps://で設定してください。"
            if not any(origin.startswith("https://") for origin in settings.CSRF_TRUSTED_ORIGINS)
            else "HTTPSのCSRF信頼済みURLがあります。",
        ),
        DeploymentCheck(
            "approved_rules",
            "承認済みルール",
            _status(RuleVersion.objects.filter(active=True, approved_at__isnull=False).exists()),
            "本番判定に使う承認済みRuleVersionを登録してください。"
            if not RuleVersion.objects.filter(active=True, approved_at__isnull=False).exists()
            else "承認済みルールがあります。",
        ),
        DeploymentCheck(
            "superuser",
            "管理者アカウント",
            _status(User.objects.filter(is_superuser=True, is_active=True).exists(), warning=True),
            "createsuperuserで管理者を作成してください。"
            if not User.objects.filter(is_superuser=True, is_active=True).exists()
            else "有効な管理者があります。",
        ),
        DeploymentCheck(
            "unresolved_issues",
            "未解決エラー",
            _status(not ValidationIssue.objects.filter(resolved=False, severity=ValidationIssue.Severity.ERROR).exists(), warning=True),
            "未解決の入力・設定エラーがあります。公開前に確認してください。"
            if ValidationIssue.objects.filter(resolved=False, severity=ValidationIssue.Severity.ERROR).exists()
            else "未解決の重大エラーはありません。",
        ),
    ]
    return checks


def deployment_check_summary(checks):
    return {
        "ok": sum(1 for check in checks if check.status == "ok"),
        "warning": sum(1 for check in checks if check.status == "warning"),
        "error": sum(1 for check in checks if check.status == "error"),
    }
