from __future__ import annotations

import csv
from datetime import datetime
from io import TextIOWrapper

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    AuditEvent,
    Facility,
    Membership,
    SubmissionRecord,
    SubmissionSchedule,
    ValidationIssue,
)
from .services.date_utils import add_months, month_start
from .services.deployment_checks import deployment_check_summary, run_deployment_checks
from .services.scheduler import recalculate_facility


def health(request):
    return HttpResponse("ok", content_type="text/plain")


def _facilities_for(user):
    if user.is_superuser:
        return Facility.objects.filter(active=True)
    return Facility.objects.filter(active=True, memberships__user=user).distinct()


def _facility_from_request(request):
    facilities = _facilities_for(request.user)
    facility_id = request.GET.get("facility") or request.POST.get("facility")
    if facility_id:
        return get_object_or_404(facilities, pk=facility_id), facilities
    facility = facilities.first()
    if not facility:
        raise Http404("閲覧可能な施設がありません。管理者に権限設定を依頼してください。")
    return facility, facilities


def _can_edit(user, facility):
    if user.is_superuser:
        return True
    return Membership.objects.filter(
        user=user,
        facility=facility,
        role__in=[
            Membership.Role.ADMIN,
            Membership.Role.MANAGER,
            Membership.Role.EDITOR,
        ],
    ).exists()


def _csv_safe(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


@login_required
def dashboard(request):
    facility, facilities = _facility_from_request(request)
    today = timezone.localdate()
    this_month = month_start(today)
    schedules = facility.submission_schedules.select_related("client", "addition").filter(
        due_date__year=today.year,
        due_date__month=today.month,
    )
    status_counts = {
        row["status"]: row["count"]
        for row in schedules.values("status").annotate(count=Count("id"))
    }
    latest_snapshot = facility.life_snapshots.order_by("-snapshot_date").first()
    app_registered_count = facility.clients.filter(active=True, life_registered=True).count()
    active_client_count = facility.clients.filter(active=True).count()
    issues = facility.validation_issues.filter(resolved=False).select_related("client")[:20]

    context = {
        "facility": facility,
        "facilities": facilities,
        "can_edit": _can_edit(request.user, facility),
        "today": today,
        "status_counts": status_counts,
        "schedules": schedules[:30],
        "issues": issues,
        "latest_snapshot": latest_snapshot,
        "app_registered_count": app_registered_count,
        "active_client_count": active_client_count,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def schedule_list(request):
    facility, facilities = _facility_from_request(request)
    qs = facility.submission_schedules.select_related("client", "addition", "rule_version")
    status = request.GET.get("status")
    addition = request.GET.get("addition")
    month = request.GET.get("month")
    if status:
        qs = qs.filter(status=status)
    if addition:
        qs = qs.filter(addition_id=addition)
    if month:
        try:
            year, month_number = map(int, month.split("-"))
            qs = qs.filter(due_date__year=year, due_date__month=month_number)
        except ValueError:
            messages.warning(request, "対象月の形式が正しくありません。")
    return render(
        request,
        "core/schedule_list.html",
        {
            "facility": facility,
            "facilities": facilities,
            "schedules": qs[:500],
            "statuses": SubmissionSchedule.Status.choices,
            "additions": facility.facility_additions.select_related("addition"),
            "can_edit": _can_edit(request.user, facility),
        },
    )


@login_required
def client_list(request):
    facility, facilities = _facility_from_request(request)
    return render(
        request,
        "core/client_list.html",
        {
            "facility": facility,
            "facilities": facilities,
            "clients": facility.clients.all(),
        },
    )


@login_required
def usage_guide(request):
    facility, facilities = _facility_from_request(request)
    return render(
        request,
        "core/usage_guide.html",
        {
            "facility": facility,
            "facilities": facilities,
            "can_edit": _can_edit(request.user, facility),
        },
    )


@login_required
def deployment_check(request):
    if not request.user.is_staff:
        raise Http404()
    facility, facilities = _facility_from_request(request)
    checks = run_deployment_checks()
    return render(
        request,
        "core/deployment_check.html",
        {
            "facility": facility,
            "facilities": facilities,
            "checks": checks,
            "summary": deployment_check_summary(checks),
        },
    )


@require_POST
@login_required
def recalculate(request):
    facility, _ = _facility_from_request(request)
    if not _can_edit(request.user, facility):
        raise Http404()
    today = timezone.localdate()
    start = month_start(add_months(today, -3))
    end = month_start(add_months(today, 12))
    count = recalculate_facility(facility, start, end, actor=request.user)
    messages.success(request, f"提出予定を再計算しました。処理件数は{count}件です。")
    return redirect(f"/?facility={facility.pk}")


@require_POST
@login_required
def mark_submitted(request, schedule_id):
    schedule = get_object_or_404(
        SubmissionSchedule.objects.select_related("facility"),
        pk=schedule_id,
        facility__in=_facilities_for(request.user),
    )
    if not _can_edit(request.user, schedule.facility):
        raise Http404()
    SubmissionRecord.objects.create(
        schedule=schedule,
        submitted_by=request.user,
        source="manual",
        accepted=True,
        external_reference=request.POST.get("external_reference", "")[:120],
    )
    schedule.refresh_status()
    schedule.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(
        facility=schedule.facility,
        user=request.user,
        action="mark_submitted",
        object_type="SubmissionSchedule",
        object_id=str(schedule.pk),
        details={"external_reference": request.POST.get("external_reference", "")[:120]},
    )
    messages.success(request, "提出済みとして登録しました。")
    return redirect(request.POST.get("next") or f"/schedules/?facility={schedule.facility_id}")


@require_POST
@login_required
def bulk_mark_submitted(request):
    facility, _ = _facility_from_request(request)
    if not _can_edit(request.user, facility):
        raise Http404()
    ids = request.POST.getlist("schedule_ids")
    schedules = facility.submission_schedules.filter(pk__in=ids).exclude(status=SubmissionSchedule.Status.SUBMITTED)
    count = 0
    for schedule in schedules:
        SubmissionRecord.objects.create(
            schedule=schedule,
            submitted_by=request.user,
            source="manual",
            accepted=True,
            external_reference=request.POST.get("external_reference", "")[:120],
        )
        schedule.refresh_status()
        schedule.save(update_fields=["status", "updated_at"])
        count += 1
    AuditEvent.objects.create(
        facility=facility,
        user=request.user,
        action="bulk_mark_submitted",
        object_type="Facility",
        object_id=str(facility.pk),
        details={"count": count},
    )
    messages.success(request, f"{count}件を提出済みとして登録しました。")
    return redirect(request.POST.get("next") or f"/schedules/?facility={facility.pk}")


@require_POST
@login_required
def import_submission_records_csv(request):
    facility, _ = _facility_from_request(request)
    if not _can_edit(request.user, facility):
        raise Http404()
    upload = request.FILES.get("csv_file")
    if not upload:
        messages.error(request, "CSVファイルを選択してください。")
        return redirect(f"/schedules/?facility={facility.pk}")
    if not upload.name.lower().endswith(".csv") or upload.size > 2 * 1024 * 1024:
        messages.error(request, "CSVは2MB以下の .csv ファイルだけ取込できます。")
        return redirect(f"/schedules/?facility={facility.pk}")

    reader = csv.DictReader(TextIOWrapper(upload.file, encoding="utf-8-sig", newline=""))
    required = {"利用者管理ID", "加算", "対象月", "提出区分", "提出日"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        messages.error(request, "CSV列名が不足しています。必要列: 利用者管理ID, 加算, 対象月, 提出区分, 提出日")
        return redirect(f"/schedules/?facility={facility.pk}")

    imported = 0
    unmatched = 0
    for row in reader:
        try:
            target_month = datetime.strptime(row["対象月"].strip(), "%Y-%m").date().replace(day=1)
            submitted_at = datetime.strptime(row["提出日"].strip(), "%Y-%m-%d")
        except (ValueError, AttributeError):
            unmatched += 1
            continue
        schedule = (
            facility.submission_schedules.select_related("client", "addition")
            .filter(
                client__external_id=row["利用者管理ID"].strip(),
                addition__name=row["加算"].strip(),
                target_month=target_month,
                submission_kind=row["提出区分"].strip(),
            )
            .first()
        )
        if not schedule:
            unmatched += 1
            continue
        SubmissionRecord.objects.get_or_create(
            schedule=schedule,
            external_reference=row.get("外部参照", "")[:120],
            defaults={
                "submitted_at": timezone.make_aware(submitted_at),
                "submitted_by": request.user,
                "source": "csv",
                "accepted": True,
            },
        )
        schedule.refresh_status()
        schedule.save(update_fields=["status", "updated_at"])
        imported += 1

    AuditEvent.objects.create(
        facility=facility,
        user=request.user,
        action="import_submission_records_csv",
        object_type="Facility",
        object_id=str(facility.pk),
        details={"imported": imported, "unmatched": unmatched},
    )
    messages.success(request, f"CSV取込: {imported}件を反映、{unmatched}件は予定と照合できませんでした。")
    return redirect(f"/schedules/?facility={facility.pk}")


@login_required
def export_schedules_csv(request):
    facility, _ = _facility_from_request(request)
    qs = facility.submission_schedules.select_related("client", "addition", "rule_version").all()

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="life_schedules_{facility.code}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "施設",
        "利用者管理ID",
        "利用者表示名",
        "加算",
        "提出区分",
        "対象月",
        "評価日",
        "提出期限",
        "状態",
        "判定理由",
        "ルール版",
        "根拠資料",
    ])
    for row in qs:
        writer.writerow([
            _csv_safe(facility.name),
            _csv_safe(row.client.external_id),
            _csv_safe(row.client.display_name),
            _csv_safe(row.addition.name),
            _csv_safe(row.submission_kind),
            row.target_month.strftime("%Y-%m"),
            row.evaluation_date.isoformat(),
            row.due_date.isoformat(),
            _csv_safe(row.get_status_display()),
            _csv_safe(row.reason),
            _csv_safe(row.rule_version.version),
            _csv_safe(row.rule_version.source_title),
        ])
    return response


@login_required
def submission_import_template_csv(request):
    facility, _ = _facility_from_request(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="life_submission_import_template.csv"'
    writer = csv.writer(response)
    writer.writerow(["利用者管理ID", "加算", "対象月", "提出区分", "提出日", "外部参照"])
    sample = (
        facility.submission_schedules.select_related("client", "addition")
        .exclude(status=SubmissionSchedule.Status.SUBMITTED)
        .order_by("due_date")
        .first()
    )
    if sample:
        writer.writerow([
            _csv_safe(sample.client.external_id),
            _csv_safe(sample.addition.name),
            sample.target_month.strftime("%Y-%m"),
            sample.submission_kind,
            timezone.localdate().isoformat(),
            "",
        ])
    return response
