from django.core.management.base import BaseCommand

from core.services.deployment_checks import deployment_check_summary, run_deployment_checks


class Command(BaseCommand):
    help = "外部公開前の環境設定と最低限の運用準備を確認します。"

    def handle(self, *args, **options):
        checks = run_deployment_checks()
        summary = deployment_check_summary(checks)
        for check in checks:
            if check.status == "ok":
                style = self.style.SUCCESS
            elif check.status == "warning":
                style = self.style.WARNING
            else:
                style = self.style.ERROR
            self.stdout.write(style(f"[{check.status.upper()}] {check.label}: {check.message}"))
        self.stdout.write(
            f"summary: ok={summary['ok']} warning={summary['warning']} error={summary['error']}"
        )
        if summary["error"]:
            raise SystemExit(1)
