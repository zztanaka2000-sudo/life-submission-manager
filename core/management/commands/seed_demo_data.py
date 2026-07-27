from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.models import (
    Client,
    ClientAddition,
    ClientEvent,
    Facility,
    FacilityAddition,
    LifeRegistrationSnapshot,
    Membership,
    Organization,
    Addition,
)
from core.services.scheduler import recalculate_facility


class Command(BaseCommand):
    help = "ローカル確認用のデモ法人、施設、利用者、提出予定を作成します。"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo_admin")
        parser.add_argument("--password", default="demo-pass-2026")

    def handle(self, *args, **options):
        call_command("load_official_rules")

        User = get_user_model()
        user, _ = User.objects.update_or_create(
            username=options["username"],
            defaults={"is_staff": True, "is_superuser": True, "email": "demo@example.com"},
        )
        user.set_password(options["password"])
        user.save()

        org, _ = Organization.objects.update_or_create(
            code="demo-org",
            defaults={"name": "デモ法人"},
        )
        facility, _ = Facility.objects.update_or_create(
            organization=org,
            code="demo-facility",
            defaults={
                "name": "デモ施設",
                "service_type": Facility.ServiceType.DAY_CARE,
                "facility_number": "1370000000",
                "active": True,
            },
        )
        Membership.objects.update_or_create(
            user=user,
            facility=facility,
            defaults={"role": Membership.Role.ADMIN},
        )

        scientific = Addition.objects.get(code="scientific_care")
        individual = Addition.objects.get(code="individual_function_ii_iii")
        adl = Addition.objects.get(code="adl_maintenance")
        fa_scientific, _ = FacilityAddition.objects.update_or_create(
            facility=facility,
            addition=scientific,
            start_date=date(2026, 4, 1),
            defaults={"active": True},
        )
        fa_individual, _ = FacilityAddition.objects.update_or_create(
            facility=facility,
            addition=individual,
            start_date=date(2026, 4, 1),
            defaults={"active": True},
        )
        fa_adl, _ = FacilityAddition.objects.update_or_create(
            facility=facility,
            addition=adl,
            start_date=date(2026, 4, 1),
            defaults={"active": True},
        )

        client_a, _ = Client.objects.update_or_create(
            facility=facility,
            external_id="A-001",
            defaults={
                "display_name": "利用者A",
                "service_start_date": date(2026, 4, 5),
                "life_registered": True,
                "active": True,
            },
        )
        client_b, _ = Client.objects.update_or_create(
            facility=facility,
            external_id="A-002",
            defaults={
                "display_name": "利用者B",
                "service_start_date": date(2026, 5, 20),
                "service_end_date": date(2026, 9, 15),
                "life_registered": False,
                "active": True,
            },
        )
        client_c, _ = Client.objects.update_or_create(
            facility=facility,
            external_id="A-003",
            defaults={
                "display_name": "利用者C",
                "service_start_date": date(2026, 4, 30),
                "life_registered": True,
                "active": True,
            },
        )

        ClientAddition.objects.update_or_create(
            client=client_a,
            facility_addition=fa_individual,
            start_date=date(2026, 4, 5),
            defaults={"eligible": True},
        )
        ClientAddition.objects.update_or_create(
            client=client_a,
            facility_addition=fa_adl,
            start_date=date(2026, 4, 5),
            defaults={"eligible": True, "anchor_date": date(2026, 4, 5)},
        )
        ClientAddition.objects.update_or_create(
            client=client_b,
            facility_addition=fa_individual,
            start_date=date(2026, 5, 20),
            defaults={"eligible": True},
        )
        ClientAddition.objects.update_or_create(
            client=client_c,
            facility_addition=fa_adl,
            start_date=date(2026, 4, 30),
            defaults={"eligible": True, "anchor_date": date(2026, 4, 30)},
        )
        ClientEvent.objects.update_or_create(
            client=client_a,
            event_type=ClientEvent.EventType.PLAN_CREATED,
            event_date=date(2026, 4, 10),
            defaults={"note": "初回計画"},
        )
        ClientEvent.objects.update_or_create(
            client=client_a,
            event_type=ClientEvent.EventType.PLAN_UPDATED,
            event_date=date(2026, 7, 10),
            defaults={"note": "計画見直し"},
        )
        ClientEvent.objects.update_or_create(
            client=client_b,
            event_type=ClientEvent.EventType.HOSPITAL_ADMISSION,
            event_date=date(2026, 7, 1),
            defaults={"note": "再確認デモ"},
        )
        LifeRegistrationSnapshot.objects.update_or_create(
            facility=facility,
            snapshot_date=date(2026, 7, 1),
            defaults={"registered_count": 3},
        )

        count = recalculate_facility(
            facility,
            date(2026, 4, 1),
            date(2027, 3, 1),
            actor=user,
        )
        self.stdout.write(self.style.SUCCESS(
            f"デモデータを作成しました。ユーザー: {options['username']} / パスワード: {options['password']} / 提出予定: {count}件"
        ))
