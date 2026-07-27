from datetime import date
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Addition,
    Client,
    ClientAddition,
    ClientEvent,
    Facility,
    FacilityAddition,
    Organization,
    RuleVersion,
    LifeRegistrationSnapshot,
    Membership,
    SubmissionRecord,
    SubmissionSchedule,
    ValidationIssue,
)
from core.services.scheduler import recalculate_facility


pytestmark = pytest.mark.django_db


@pytest.fixture
def facility():
    org = Organization.objects.create(name="テスト法人", code="test-org")
    return Facility.objects.create(
        organization=org,
        name="テスト施設",
        code="test-facility",
        service_type=Facility.ServiceType.DAY_CARE,
    )


def make_rule(addition, kind, interval=3, config=None):
    return RuleVersion.objects.create(
        addition=addition,
        version="test-v1",
        rule_kind=kind,
        effective_from=date(2024, 4, 1),
        interval_months=interval,
        due_month_offset=1,
        due_day=10,
        service_types=[],
        config=config or {},
        source_title="テスト根拠",
        source_url="https://example.com/rule.pdf",
        source_published_on=date(2024, 3, 15),
        approved_at=timezone.now(),
    )


def test_scientific_initial_periodic_and_end(facility):
    addition = Addition.objects.create(
        code="scientific",
        name="科学的介護",
        applies_to_all_active=True,
    )
    make_rule(
        addition,
        RuleVersion.RuleKind.SCIENTIFIC_CARE,
        interval=3,
        config={"recurring": True, "end_submission": True},
    )
    FacilityAddition.objects.create(
        facility=facility,
        addition=addition,
        start_date=date(2025, 1, 1),
    )
    client = Client.objects.create(
        facility=facility,
        external_id="A001",
        display_name="利用者A",
        service_start_date=date(2025, 1, 15),
        service_end_date=date(2025, 8, 20),
        life_registered=True,
    )

    recalculate_facility(facility, date(2025, 1, 1), date(2025, 12, 1))
    rows = list(
        SubmissionSchedule.objects.filter(client=client).order_by("target_month").values_list(
            "target_month", "submission_kind", "due_date"
        )
    )
    assert (date(2025, 1, 1), "initial", date(2025, 2, 10)) in rows
    assert (date(2025, 4, 1), "periodic", date(2025, 5, 10)) in rows
    assert (date(2025, 7, 1), "periodic", date(2025, 8, 10)) in rows
    assert (date(2025, 8, 1), "end", date(2025, 9, 10)) in rows


def test_individual_function_uses_plan_events(facility):
    addition = Addition.objects.create(
        code="individual",
        name="個別機能訓練",
        applies_to_all_active=False,
    )
    make_rule(
        addition,
        RuleVersion.RuleKind.INDIVIDUAL_FUNCTION,
        interval=3,
        config={"event_types": ["plan_created", "plan_updated"], "recurring": True},
    )
    fa = FacilityAddition.objects.create(
        facility=facility,
        addition=addition,
        start_date=date(2025, 1, 1),
    )
    client = Client.objects.create(
        facility=facility,
        external_id="B001",
        display_name="利用者B",
        service_start_date=date(2025, 1, 1),
        life_registered=True,
    )
    ClientAddition.objects.create(
        client=client,
        facility_addition=fa,
        start_date=date(2025, 1, 1),
    )
    ClientEvent.objects.create(
        client=client,
        event_type=ClientEvent.EventType.PLAN_CREATED,
        event_date=date(2025, 1, 20),
    )
    ClientEvent.objects.create(
        client=client,
        event_type=ClientEvent.EventType.PLAN_UPDATED,
        event_date=date(2025, 5, 2),
    )

    recalculate_facility(facility, date(2025, 1, 1), date(2025, 12, 1))
    kinds = set(
        SubmissionSchedule.objects.filter(client=client).values_list(
            "target_month", "submission_kind"
        )
    )
    assert (date(2025, 1, 1), "plan_created") in kinds
    assert (date(2025, 4, 1), "periodic") in kinds
    assert (date(2025, 5, 1), "plan_updated") in kinds
    assert (date(2025, 8, 1), "periodic") in kinds


def test_mid_month_client_addition_start_counts_for_target_month(facility):
    addition = Addition.objects.create(
        code="individual-mid-month",
        name="個別機能訓練（月中開始）",
        applies_to_all_active=False,
    )
    make_rule(
        addition,
        RuleVersion.RuleKind.INDIVIDUAL_FUNCTION,
        interval=3,
        config={"event_types": ["plan_created"], "recurring": True},
    )
    fa = FacilityAddition.objects.create(
        facility=facility,
        addition=addition,
        start_date=date(2025, 4, 1),
    )
    client = Client.objects.create(
        facility=facility,
        external_id="B002",
        display_name="利用者B2",
        service_start_date=date(2025, 4, 5),
        life_registered=True,
    )
    ClientAddition.objects.create(
        client=client,
        facility_addition=fa,
        start_date=date(2025, 4, 5),
    )
    ClientEvent.objects.create(
        client=client,
        event_type=ClientEvent.EventType.PLAN_CREATED,
        event_date=date(2025, 4, 10),
    )

    recalculate_facility(facility, date(2025, 4, 1), date(2025, 7, 1))

    assert SubmissionSchedule.objects.filter(
        client=client,
        addition=addition,
        target_month=date(2025, 4, 1),
        submission_kind=SubmissionSchedule.SubmissionKind.PLAN_CREATED,
    ).exists()


def test_adl_initial_and_six_month(facility):
    addition = Addition.objects.create(
        code="adl",
        name="ADL維持等",
        applies_to_all_active=False,
    )
    make_rule(
        addition,
        RuleVersion.RuleKind.ADL_MAINTENANCE,
        interval=6,
        config={"offsets_months": [0, 6]},
    )
    fa = FacilityAddition.objects.create(
        facility=facility,
        addition=addition,
        start_date=date(2025, 1, 1),
    )
    client = Client.objects.create(
        facility=facility,
        external_id="C001",
        display_name="利用者C",
        service_start_date=date(2025, 1, 1),
        life_registered=True,
    )
    ClientAddition.objects.create(
        client=client,
        facility_addition=fa,
        start_date=date(2025, 1, 1),
        anchor_date=date(2025, 1, 10),
    )

    recalculate_facility(facility, date(2025, 1, 1), date(2025, 12, 1))
    rows = set(
        SubmissionSchedule.objects.filter(client=client).values_list(
            "target_month", "submission_kind", "due_date"
        )
    )
    assert (date(2025, 1, 1), "adl_initial", date(2025, 2, 10)) in rows
    assert (date(2025, 7, 1), "adl_six_month", date(2025, 8, 10)) in rows


def test_unapproved_rules_are_not_used(facility):
    addition = Addition.objects.create(code="draft", name="未承認加算")
    RuleVersion.objects.create(
        addition=addition,
        version="draft-v1",
        rule_kind=RuleVersion.RuleKind.GENERIC_INTERVAL,
        effective_from=date(2025, 1, 1),
        source_title="未承認根拠",
        source_url="https://example.com/draft.pdf",
        source_published_on=date(2025, 1, 1),
    )
    FacilityAddition.objects.create(facility=facility, addition=addition, start_date=date(2025, 1, 1))
    Client.objects.create(
        facility=facility,
        external_id="D001",
        display_name="利用者D",
        service_start_date=date(2025, 1, 1),
        life_registered=True,
    )

    recalculate_facility(facility, date(2025, 1, 1), date(2025, 3, 1))

    assert SubmissionSchedule.objects.count() == 0
    assert ValidationIssue.objects.filter(code="NO_ACTIVE_RULE_draft", resolved=False).exists()


def test_recalculation_is_idempotent_and_keeps_submitted_records(facility):
    addition = Addition.objects.create(code="generic", name="汎用")
    make_rule(addition, RuleVersion.RuleKind.GENERIC_INTERVAL, interval=1)
    FacilityAddition.objects.create(facility=facility, addition=addition, start_date=date(2025, 1, 1))
    client = Client.objects.create(
        facility=facility,
        external_id="E001",
        display_name="利用者E",
        service_start_date=date(2025, 1, 1),
        life_registered=True,
    )

    recalculate_facility(facility, date(2025, 1, 1), date(2025, 3, 1))
    first_count = SubmissionSchedule.objects.count()
    schedule = SubmissionSchedule.objects.filter(client=client, target_month=date(2025, 1, 1)).get()
    SubmissionRecord.objects.create(schedule=schedule, source="manual", accepted=True)
    recalculate_facility(facility, date(2025, 1, 1), date(2025, 3, 1))

    assert SubmissionSchedule.objects.count() == first_count
    schedule.refresh_from_db()
    assert schedule.status == SubmissionSchedule.Status.SUBMITTED
    assert schedule.records.filter(accepted=True).count() == 1


def test_life_registration_count_mismatch_creates_issue(facility):
    Addition.objects.create(code="x", name="確認用")
    Client.objects.create(
        facility=facility,
        external_id="F001",
        display_name="利用者F",
        service_start_date=date(2025, 1, 1),
        life_registered=True,
    )
    LifeRegistrationSnapshot.objects.create(
        facility=facility,
        snapshot_date=date(2025, 1, 31),
        registered_count=2,
    )

    recalculate_facility(facility, date(2025, 1, 1), date(2025, 1, 1))

    assert ValidationIssue.objects.filter(code="LIFE_REGISTRATION_COUNT_MISMATCH", resolved=False).exists()


def test_viewer_cannot_mark_other_facility_schedule_submitted(client, facility):
    user = get_user_model().objects.create_user(username="viewer", password="pass")
    other_org = Organization.objects.create(name="別法人", code="other-org")
    other_facility = Facility.objects.create(
        organization=other_org,
        name="別施設",
        code="other-facility",
        service_type=Facility.ServiceType.DAY_CARE,
    )
    Membership.objects.create(user=user, facility=facility, role=Membership.Role.VIEWER)
    addition = Addition.objects.create(code="tenant", name="施設分離加算")
    rule = make_rule(addition, RuleVersion.RuleKind.GENERIC_INTERVAL, interval=1)
    other_client = Client.objects.create(
        facility=other_facility,
        external_id="G001",
        display_name="別施設利用者",
        service_start_date=date(2025, 1, 1),
        life_registered=True,
    )
    schedule = SubmissionSchedule.objects.create(
        facility=other_facility,
        client=other_client,
        addition=addition,
        rule_version=rule,
        target_month=date(2025, 1, 1),
        evaluation_date=date(2025, 1, 1),
        due_date=date(2025, 2, 10),
        submission_kind=SubmissionSchedule.SubmissionKind.INITIAL,
        reason="test",
    )

    client.login(username="viewer", password="pass")
    response = client.post(reverse("mark_submitted", args=[schedule.pk]), secure=True)

    assert response.status_code == 404
    assert SubmissionRecord.objects.count() == 0
