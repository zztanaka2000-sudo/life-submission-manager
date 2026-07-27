from datetime import date
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Addition, RuleVersion


SOURCE_TITLE = "科学的介護情報システム（LIFE）関連加算に関する基本的な考え方並びに事務処理手順及び様式例の提示について"
SOURCE_URL = "https://www.mhlw.go.jp/content/12300000/001227990.pdf"
SOURCE_DATE = date(2024, 3, 15)


class Command(BaseCommand):
    help = "厚生労働省通知を根拠に、初期ルール候補を登録します。適用前に管理者が確認してください。"

    def handle(self, *args, **options):
        additions = [
            {
                "code": "scientific_care",
                "name": "科学的介護推進体制加算",
                "all": True,
                "rule_kind": RuleVersion.RuleKind.SCIENTIFIC_CARE,
                "interval": 3,
                "config": {"recurring": True, "end_submission": True},
                "summary": "算定開始月または利用開始月、少なくとも3月ごと、利用終了月。対象月の翌月10日まで。",
            },
            {
                "code": "individual_function_ii_iii",
                "name": "個別機能訓練加算（Ⅱ）・（Ⅲ）",
                "all": False,
                "rule_kind": RuleVersion.RuleKind.INDIVIDUAL_FUNCTION,
                "interval": 3,
                "config": {
                    "event_types": ["plan_created", "plan_updated"],
                    "recurring": True,
                    "end_submission": False,
                },
                "summary": "個別機能訓練計画の新規作成月、変更月、そのほか少なくとも3月に1回。対象月の翌月10日まで。",
            },
            {
                "code": "adl_maintenance",
                "name": "ADL維持等加算",
                "all": False,
                "rule_kind": RuleVersion.RuleKind.ADL_MAINTENANCE,
                "interval": 6,
                "config": {"offsets_months": [0, 6], "end_submission": False},
                "summary": "評価対象利用開始月と、その翌月から起算して6月目の月。対象月の翌月10日まで。",
            },
        ]

        for data in additions:
            addition, _ = Addition.objects.update_or_create(
                code=data["code"],
                defaults={
                    "name": data["name"],
                    "applies_to_all_active": data["all"],
                    "active": True,
                },
            )
            rule, created = RuleVersion.objects.update_or_create(
                addition=addition,
                version="R6-2024-03-15",
                defaults={
                    "rule_kind": data["rule_kind"],
                    "effective_from": date(2024, 4, 1),
                    "effective_to": None,
                    "interval_months": data["interval"],
                    "due_month_offset": 1,
                    "due_day": 10,
                    "service_types": [],
                    "config": data["config"],
                    "source_title": SOURCE_TITLE,
                    "source_url": SOURCE_URL,
                    "source_published_on": SOURCE_DATE,
                    "change_summary": data["summary"],
                    "active": True,
                    "approved_at": timezone.now(),
                },
            )
            self.stdout.write(self.style.SUCCESS(
                f"{'作成' if created else '更新'}: {addition.name} / {rule.version}"
            ))

        other, _ = Addition.objects.update_or_create(
            code="life_other",
            defaults={
                "name": "その他のLIFE関連項目",
                "applies_to_all_active": False,
                "active": True,
            },
        )
        self.stdout.write(self.style.WARNING(
            "その他のLIFE関連項目は加算・サービス別に要件が異なるため、自動ルールは作成していません。"
        ))
