from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import (
    AuditEvent,
    Client,
    ClientAddition,
    ClientEvent,
    Facility,
    FacilityAddition,
    RuleVersion,
    SubmissionSchedule,
    ValidationIssue,
)
from .date_utils import add_months, due_date_for, iter_months, month_end, month_start


@dataclass(frozen=True)
class ScheduleCandidate:
    target_month: date
    evaluation_date: date
    kind: str
    reason: str


def _rule_for(facility_addition: FacilityAddition, target_date: date):
    rules = facility_addition.addition.rule_versions.filter(
        active=True,
        approved_at__isnull=False,
        effective_from__lte=target_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=target_date))
    for rule in rules.order_by("-effective_from"):
        if rule.applies(facility_addition.facility, target_date):
            return rule
    return None


def _client_is_assigned(client: Client, facility_addition: FacilityAddition, target_date: date):
    if facility_addition.addition.applies_to_all_active:
        return True
    target_start = month_start(target_date)
    target_end = month_end(target_date)
    return ClientAddition.objects.filter(
        client=client,
        facility_addition=facility_addition,
        eligible=True,
        start_date__lte=target_end,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=target_start)).exists()


def _scientific_candidates(client, facility_addition, rule, start, end):
    anchor = max(month_start(client.service_start_date), month_start(facility_addition.start_date))
    candidates = []
    if start <= anchor <= end:
        existing = client.service_start_date < facility_addition.start_date
        reason = (
            "加算算定開始月にサービス利用中のため"
            if existing
            else "サービス利用開始月のため"
        )
        candidates.append(
            ScheduleCandidate(anchor, max(client.service_start_date, facility_addition.start_date), "initial", reason)
        )

    if rule.config.get("recurring", True):
        interval = max(1, rule.interval_months)
        for target in iter_months(add_months(anchor, interval), end, interval):
            if target >= start and client.active_on(target) and facility_addition.active_on(target):
                candidates.append(
                    ScheduleCandidate(target, target, "periodic", f"少なくとも{interval}月ごとの定期提出")
                )

    if rule.config.get("end_submission", True) and client.service_end_date:
        end_month = month_start(client.service_end_date)
        if start <= end_month <= end and facility_addition.active_on(client.service_end_date):
            candidates.append(
                ScheduleCandidate(end_month, client.service_end_date, "end", "サービス利用終了月のため")
            )
    return candidates


def _individual_function_candidates(client, facility_addition, rule, start, end):
    event_types = rule.config.get("event_types", ["plan_created", "plan_updated"])
    events = list(
        client.events.filter(
            event_type__in=event_types,
            event_date__lte=end,
        ).order_by("event_date", "id")
    )
    candidates = []
    for event in events:
        target = month_start(event.event_date)
        if start <= target <= end and facility_addition.active_on(event.event_date) and _client_is_assigned(client, facility_addition, target):
            kind = "plan_created" if event.event_type == ClientEvent.EventType.PLAN_CREATED else "plan_updated"
            candidates.append(
                ScheduleCandidate(target, event.event_date, kind, event.get_event_type_display())
            )

    if rule.config.get("recurring", True) and events:
        interval = max(1, rule.interval_months)
        for idx, event in enumerate(events):
            anchor = month_start(event.event_date)
            next_event_month = (
                month_start(events[idx + 1].event_date) if idx + 1 < len(events) else add_months(end, 1)
            )
            for target in iter_months(add_months(anchor, interval), end, interval):
                if target >= next_event_month:
                    break
                if target >= start and client.active_on(target) and facility_addition.active_on(target) and _client_is_assigned(client, facility_addition, target):
                    candidates.append(
                        ScheduleCandidate(target, target, "periodic", f"計画作成・変更月以外の少なくとも{interval}月ごとの提出")
                    )

    if not events:
        _upsert_issue(
            facility=client.facility,
            client=client,
            code="MISSING_FUNCTION_PLAN_EVENT",
            severity=ValidationIssue.Severity.ERROR,
            message=f"{facility_addition.addition.name}の計画作成日または変更日が未登録です。",
        )
    return candidates


def _adl_candidates(client, facility_addition, rule, start, end):
    assignment = (
        ClientAddition.objects.filter(
            client=client,
            facility_addition=facility_addition,
            eligible=True,
        )
        .order_by("-start_date")
        .first()
    )
    anchor = assignment.anchor_date if assignment and assignment.anchor_date else None
    if not anchor:
        _upsert_issue(
            facility=client.facility,
            client=client,
            code="MISSING_ADL_ANCHOR",
            severity=ValidationIssue.Severity.ERROR,
            message="ADL維持等加算の評価対象利用開始月に相当する基準日が未登録です。",
        )
        return []

    offsets = rule.config.get("offsets_months", [0, 6])
    result = []
    for offset in offsets:
        target = month_start(add_months(anchor, int(offset)))
        if start <= target <= end and _client_is_assigned(client, facility_addition, target):
            kind = "adl_initial" if int(offset) == 0 else "adl_six_month"
            reason = "評価対象利用開始月" if int(offset) == 0 else "評価対象利用開始月の翌月から起算した6月目"
            result.append(ScheduleCandidate(target, add_months(anchor, int(offset)), kind, reason))
    return result


def _generic_candidates(client, facility_addition, rule, start, end):
    assignment = (
        ClientAddition.objects.filter(
            client=client,
            facility_addition=facility_addition,
            eligible=True,
        )
        .order_by("-start_date")
        .first()
    )
    anchor = (
        assignment.anchor_date
        if assignment and assignment.anchor_date
        else max(client.service_start_date, facility_addition.start_date)
    )
    interval = max(1, rule.interval_months)
    result = []
    for target in iter_months(month_start(anchor), end, interval):
        if target >= start and client.active_on(target) and facility_addition.active_on(target) and _client_is_assigned(client, facility_addition, target):
            kind = "initial" if target == month_start(anchor) else "periodic"
            result.append(ScheduleCandidate(target, target, kind, f"{interval}月間隔の設定ルール"))
    return result


def _candidates(client, facility_addition, rule, start, end):
    if rule.rule_kind == RuleVersion.RuleKind.SCIENTIFIC_CARE:
        return _scientific_candidates(client, facility_addition, rule, start, end)
    if rule.rule_kind == RuleVersion.RuleKind.INDIVIDUAL_FUNCTION:
        return _individual_function_candidates(client, facility_addition, rule, start, end)
    if rule.rule_kind == RuleVersion.RuleKind.ADL_MAINTENANCE:
        return _adl_candidates(client, facility_addition, rule, start, end)
    return _generic_candidates(client, facility_addition, rule, start, end)


def _upsert_issue(*, facility, code, severity, message, client=None, details=None):
    issue, _ = ValidationIssue.objects.update_or_create(
        facility=facility,
        client=client,
        code=code,
        resolved=False,
        defaults={
            "severity": severity,
            "message": message,
            "details": details or {},
        },
    )
    return issue


def validate_facility(facility: Facility):
    ValidationIssue.objects.filter(facility=facility, resolved=False).update(
        resolved=True, resolved_at=timezone.now()
    )

    if not facility.clients.filter(active=True).exists():
        _upsert_issue(
            facility=facility,
            code="NO_ACTIVE_CLIENTS",
            severity=ValidationIssue.Severity.INFO,
            message="有効な利用者が登録されていません。",
        )

    for client in facility.clients.filter(active=True):
        if not client.service_start_date:
            _upsert_issue(
                facility=facility,
                client=client,
                code="MISSING_SERVICE_START",
                severity=ValidationIssue.Severity.ERROR,
                message="利用開始日が未入力です。",
            )
        if not client.life_registered:
            _upsert_issue(
                facility=facility,
                client=client,
                code="LIFE_CLIENT_NOT_REGISTERED",
                severity=ValidationIssue.Severity.WARNING,
                message="施設内では有効ですが、LIFE登録済みの確認が取れていません。",
            )

        if client.events.filter(
            event_type__in=[
                ClientEvent.EventType.HOSPITAL_ADMISSION,
                ClientEvent.EventType.HOSPITAL_DISCHARGE,
                ClientEvent.EventType.SERVICE_RESTART,
            ]
        ).exists():
            _upsert_issue(
                facility=facility,
                client=client,
                code="EVENT_RECALCULATION_REVIEW",
                severity=ValidationIssue.Severity.WARNING,
                message="入退院または利用再開の履歴があります。制度上の取扱いを確認し、必要に応じて基準日を更新してください。",
            )

    for facility_addition in facility.facility_additions.filter(active=True):
        if not _rule_for(facility_addition, timezone.localdate()):
            _upsert_issue(
                facility=facility,
                code=f"NO_ACTIVE_RULE_{facility_addition.addition.code}",
                severity=ValidationIssue.Severity.ERROR,
                message=f"{facility_addition.addition.name}に現在適用できる承認済みルールがありません。",
            )
        rules = list(
            facility_addition.addition.rule_versions.filter(active=True, approved_at__isnull=False)
            .order_by("effective_from", "id")
        )
        for idx, rule in enumerate(rules):
            if rule.service_types and facility.service_type not in rule.service_types:
                continue
            for other in rules[idx + 1 :]:
                if other.service_types and facility.service_type not in other.service_types:
                    continue
                rule_end = rule.effective_to or date.max
                other_end = other.effective_to or date.max
                if rule.effective_from <= other_end and other.effective_from <= rule_end:
                    _upsert_issue(
                        facility=facility,
                        code=f"OVERLAPPING_RULE_{facility_addition.addition.code}",
                        severity=ValidationIssue.Severity.ERROR,
                        message=f"{facility_addition.addition.name}の承認済みルール適用期間が重複しています。",
                        details={"rule": rule.version, "other_rule": other.version},
                    )

    snapshot = facility.life_snapshots.order_by("-snapshot_date").first()
    if snapshot:
        app_registered = facility.clients.filter(active=True, life_registered=True).count()
        if app_registered != snapshot.registered_count:
            _upsert_issue(
                facility=facility,
                code="LIFE_REGISTRATION_COUNT_MISMATCH",
                severity=ValidationIssue.Severity.ERROR,
                message=f"LIFE登録人数は{snapshot.registered_count}名、アプリ上の登録済み人数は{app_registered}名です。",
                details={
                    "snapshot_date": snapshot.snapshot_date.isoformat(),
                    "life_registered_count": snapshot.registered_count,
                    "app_registered_count": app_registered,
                },
            )


@transaction.atomic
def recalculate_facility(
    facility: Facility,
    start: date,
    end: date,
    *,
    actor=None,
    warning_days: int = 14,
):
    start = month_start(start)
    end = month_start(end)
    validate_facility(facility)
    generated_keys = set()
    created_or_updated = 0

    clients = facility.clients.filter(active=True).prefetch_related("events", "client_additions")
    facility_additions = facility.facility_additions.filter(active=True).select_related("addition")

    for facility_addition in facility_additions:
        for client in clients:
            overlap_start = max(start, month_start(client.service_start_date), month_start(facility_addition.start_date))
            client_end = month_start(client.service_end_date) if client.service_end_date else end
            addition_end = month_start(facility_addition.end_date) if facility_addition.end_date else end
            overlap_end = min(end, client_end, addition_end)
            if overlap_start > overlap_end:
                continue
            if not _client_is_assigned(client, facility_addition, overlap_start):
                continue

            rule = _rule_for(facility_addition, overlap_start)
            if not rule:
                continue

            for candidate in _candidates(client, facility_addition, rule, overlap_start, overlap_end):
                due = due_date_for(candidate.target_month, rule.due_month_offset, rule.due_day)
                key = (
                    client.id,
                    facility_addition.addition_id,
                    candidate.target_month,
                    candidate.kind,
                )
                generated_keys.add(key)
                schedule, _ = SubmissionSchedule.objects.update_or_create(
                    client=client,
                    addition=facility_addition.addition,
                    target_month=candidate.target_month,
                    submission_kind=candidate.kind,
                    defaults={
                        "facility": facility,
                        "rule_version": rule,
                        "evaluation_date": candidate.evaluation_date,
                        "due_date": due,
                        "reason": candidate.reason,
                        "generated": True,
                        "computed_at": timezone.now(),
                    },
                )
                schedule.refresh_status(warning_days=warning_days)
                schedule.save(update_fields=["status", "updated_at"])
                created_or_updated += 1

    stale = SubmissionSchedule.objects.filter(
        facility=facility,
        generated=True,
        target_month__gte=start,
        target_month__lte=end,
    )
    for schedule in stale:
        key = (
            schedule.client_id,
            schedule.addition_id,
            schedule.target_month,
            schedule.submission_kind,
        )
        if key not in generated_keys and not schedule.records.filter(accepted=True).exists():
            schedule.delete()

    AuditEvent.objects.create(
        facility=facility,
        user=actor,
        action="recalculate_schedules",
        object_type="Facility",
        object_id=str(facility.pk),
        details={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "created_or_updated": created_or_updated,
        },
    )
    return created_or_updated
