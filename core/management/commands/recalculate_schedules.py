from datetime import date
from django.core.management.base import BaseCommand, CommandError
from core.models import Facility
from core.services.scheduler import recalculate_facility


class Command(BaseCommand):
    help = "指定施設の提出予定を再計算します。"

    def add_arguments(self, parser):
        parser.add_argument("--facility", type=int, required=True)
        parser.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
        parser.add_argument("--end", type=str, required=True, help="YYYY-MM-DD")

    def handle(self, *args, **options):
        try:
            facility = Facility.objects.get(pk=options["facility"])
            start = date.fromisoformat(options["start"])
            end = date.fromisoformat(options["end"])
        except (Facility.DoesNotExist, ValueError) as exc:
            raise CommandError(str(exc))
        count = recalculate_facility(facility, start, end)
        self.stdout.write(self.style.SUCCESS(f"{count}件を処理しました。"))
