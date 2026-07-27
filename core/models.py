from __future__ import annotations

from datetime import date, timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(TimeStampedModel):
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80, unique=True)

    def __str__(self):
        return self.name


class Facility(TimeStampedModel):
    class ServiceType(models.TextChoices):
        DAY_CARE = "day_care", "通所介護"
        SPECIFIC_FACILITY = "specific_facility", "特定施設入居者生活介護"
        NURSING_HOME = "nursing_home", "介護老人福祉施設"
        GERIATRIC_HEALTH = "geriatric_health", "介護老人保健施設"
        MEDICAL_CARE = "medical_care", "介護医療院"
        HOME_REHAB = "home_rehab", "訪問リハビリテーション"
        DAY_REHAB = "day_rehab", "通所リハビリテーション"
        OTHER = "other", "その他"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="facilities")
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80)
    service_type = models.CharField(max_length=40, choices=ServiceType.choices)
    facility_number = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="unique_facility_code_per_org")
        ]
        ordering = ["organization__name", "name"]

    def __str__(self):
        return f"{self.organization.name} / {self.name}"


class Membership(TimeStampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "法人管理者"
        MANAGER = "manager", "施設管理者"
        EDITOR = "editor", "入力担当"
        VIEWER = "viewer", "閲覧のみ"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="facility_memberships")
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "facility"], name="unique_user_facility_membership")
        ]

    def __str__(self):
        return f"{self.user} / {self.facility} / {self.get_role_display()}"


class Client(TimeStampedModel):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="clients")
    external_id = models.CharField(max_length=80)
    display_name = models.CharField(
        max_length=120,
        help_text="実名ではなく施設内管理番号や仮名での運用を推奨します。",
    )
    service_start_date = models.DateField()
    service_end_date = models.DateField(null=True, blank=True)
    life_registered = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "external_id"], name="unique_client_external_id")
        ]
        ordering = ["display_name"]

    def clean(self):
        if self.service_end_date and self.service_end_date < self.service_start_date:
            raise ValidationError("利用終了日は利用開始日以降にしてください。")

    def active_on(self, target_date: date) -> bool:
        return (
            self.service_start_date <= target_date
            and (self.service_end_date is None or self.service_end_date >= target_date)
        )

    def __str__(self):
        return f"{self.facility.name} / {self.display_name}"


class Addition(TimeStampedModel):
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    applies_to_all_active = models.BooleanField(
        default=True,
        help_text="施設で算定中の場合、原則として全利用者を対象候補にするか。",
    )
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class FacilityAddition(TimeStampedModel):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="facility_additions")
    addition = models.ForeignKey(Addition, on_delete=models.PROTECT, related_name="facility_additions")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "addition", "start_date"],
                name="unique_facility_addition_start",
            )
        ]
        ordering = ["facility", "addition__name", "-start_date"]

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("算定終了日は算定開始日以降にしてください。")

    def active_on(self, target_date: date) -> bool:
        return (
            self.active
            and self.start_date <= target_date
            and (self.end_date is None or self.end_date >= target_date)
        )

    def __str__(self):
        return f"{self.facility.name} / {self.addition.name}"


class ClientAddition(TimeStampedModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client_additions")
    facility_addition = models.ForeignKey(
        FacilityAddition, on_delete=models.CASCADE, related_name="client_assignments"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    anchor_date = models.DateField(
        null=True,
        blank=True,
        help_text="ADL維持等加算の評価対象利用開始月など、ルール計算の基準日。",
    )
    eligible = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client", "facility_addition", "start_date"],
                name="unique_client_addition_start",
            )
        ]

    def clean(self):
        if self.client_id and self.facility_addition_id:
            if self.client.facility_id != self.facility_addition.facility_id:
                raise ValidationError("利用者と加算設定の施設が一致していません。")
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("終了日は開始日以降にしてください。")

    def __str__(self):
        return f"{self.client.display_name} / {self.facility_addition.addition.name}"


class ClientEvent(TimeStampedModel):
    class EventType(models.TextChoices):
        HOSPITAL_ADMISSION = "hospital_admission", "入院"
        HOSPITAL_DISCHARGE = "hospital_discharge", "退院"
        SERVICE_RESTART = "service_restart", "利用再開"
        SERVICE_END = "service_end", "利用終了"
        PLAN_CREATED = "plan_created", "個別機能訓練計画作成"
        PLAN_UPDATED = "plan_updated", "個別機能訓練計画変更"
        OTHER = "other", "その他"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    event_date = models.DateField()
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["client", "event_date", "id"]

    def __str__(self):
        return f"{self.client.display_name} / {self.get_event_type_display()} / {self.event_date}"


class RuleVersion(TimeStampedModel):
    class RuleKind(models.TextChoices):
        SCIENTIFIC_CARE = "scientific_care", "科学的介護"
        INDIVIDUAL_FUNCTION = "individual_function", "個別機能訓練"
        ADL_MAINTENANCE = "adl_maintenance", "ADL維持等"
        GENERIC_INTERVAL = "generic_interval", "汎用定期提出"

    addition = models.ForeignKey(Addition, on_delete=models.CASCADE, related_name="rule_versions")
    version = models.CharField(max_length=40)
    rule_kind = models.CharField(max_length=40, choices=RuleKind.choices)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    interval_months = models.PositiveSmallIntegerField(default=3)
    due_month_offset = models.PositiveSmallIntegerField(default=1)
    due_day = models.PositiveSmallIntegerField(default=10)
    service_types = models.JSONField(
        default=list,
        blank=True,
        help_text='空配列は全サービス種別。例: ["day_care", "specific_facility"]',
    )
    config = models.JSONField(default=dict, blank=True)
    source_title = models.CharField(max_length=300)
    source_url = models.URLField(max_length=800)
    source_published_on = models.DateField()
    change_summary = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_life_rules",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["addition", "version"], name="unique_rule_version")
        ]
        ordering = ["addition__name", "-effective_from"]

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError("適用終了日は適用開始日以降にしてください。")
        if not 1 <= self.due_day <= 28:
            raise ValidationError("提出期限日は1日から28日の範囲で設定してください。")

    def applies(self, facility: Facility, target_date: date) -> bool:
        service_ok = not self.service_types or facility.service_type in self.service_types
        date_ok = self.effective_from <= target_date and (
            self.effective_to is None or self.effective_to >= target_date
        )
        return self.active and service_ok and date_ok

    def __str__(self):
        return f"{self.addition.name} / {self.version}"


class SubmissionSchedule(TimeStampedModel):
    class SubmissionKind(models.TextChoices):
        INITIAL = "initial", "初回提出"
        PERIODIC = "periodic", "定期提出"
        END = "end", "終了時提出"
        PLAN_CREATED = "plan_created", "計画作成時"
        PLAN_UPDATED = "plan_updated", "計画変更時"
        ADL_INITIAL = "adl_initial", "ADL初月"
        ADL_SIX_MONTH = "adl_six_month", "ADL6月目"
        MANUAL_REVIEW = "manual_review", "要確認"

    class Status(models.TextChoices):
        PENDING = "pending", "未提出"
        DUE_SOON = "due_soon", "期限接近"
        OVERDUE = "overdue", "期限超過"
        SUBMITTED = "submitted", "提出済み"
        NOT_REQUIRED = "not_required", "対象外"
        REVIEW = "review", "要確認"

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="submission_schedules")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="submission_schedules")
    addition = models.ForeignKey(Addition, on_delete=models.PROTECT, related_name="submission_schedules")
    rule_version = models.ForeignKey(
        RuleVersion, on_delete=models.PROTECT, related_name="submission_schedules"
    )
    target_month = models.DateField(help_text="評価・提出対象月の月初日")
    evaluation_date = models.DateField()
    due_date = models.DateField()
    submission_kind = models.CharField(max_length=30, choices=SubmissionKind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reason = models.CharField(max_length=500)
    generated = models.BooleanField(default=True)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client", "addition", "target_month", "submission_kind"],
                name="unique_submission_schedule",
            )
        ]
        ordering = ["due_date", "facility", "client__display_name"]

    def refresh_status(self, today=None, warning_days=14):
        today = today or timezone.localdate()
        if self.records.filter(accepted=True).exists():
            self.status = self.Status.SUBMITTED
        elif self.status == self.Status.NOT_REQUIRED:
            pass
        elif self.due_date < today:
            self.status = self.Status.OVERDUE
        elif self.due_date <= today + timedelta(days=warning_days):
            self.status = self.Status.DUE_SOON
        else:
            self.status = self.Status.PENDING
        return self.status

    def __str__(self):
        return f"{self.client.display_name} / {self.addition.name} / {self.target_month:%Y-%m}"


class SubmissionRecord(TimeStampedModel):
    schedule = models.ForeignKey(SubmissionSchedule, on_delete=models.CASCADE, related_name="records")
    submitted_at = models.DateTimeField(default=timezone.now)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="life_submission_records",
    )
    source = models.CharField(
        max_length=30,
        choices=[
            ("manual", "手動登録"),
            ("csv", "CSV取込"),
            ("system", "システム連携"),
        ],
        default="manual",
    )
    accepted = models.BooleanField(default=True)
    external_reference = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.schedule} / {self.submitted_at:%Y-%m-%d}"


class LifeRegistrationSnapshot(TimeStampedModel):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="life_snapshots")
    snapshot_date = models.DateField()
    registered_count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "snapshot_date"], name="unique_life_snapshot_date"
            )
        ]
        ordering = ["-snapshot_date"]

    def __str__(self):
        return f"{self.facility.name} / {self.snapshot_date} / {self.registered_count}名"


class ValidationIssue(TimeStampedModel):
    class Severity(models.TextChoices):
        INFO = "info", "情報"
        WARNING = "warning", "警告"
        ERROR = "error", "エラー"

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="validation_issues")
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, null=True, blank=True, related_name="validation_issues"
    )
    code = models.CharField(max_length=80)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    message = models.CharField(max_length=500)
    details = models.JSONField(default=dict, blank=True)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["facility", "resolved", "severity"], name="issue_facility_status_idx")
        ]
        ordering = ["resolved", "-severity", "-created_at"]

    def __str__(self):
        return f"{self.facility.name} / {self.code} / {self.message}"


class AuditEvent(TimeStampedModel):
    facility = models.ForeignKey(
        Facility, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at} / {self.action}"
