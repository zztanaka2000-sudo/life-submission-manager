from django.contrib import admin
from .models import (
    Addition,
    AuditEvent,
    Client,
    ClientAddition,
    ClientEvent,
    Facility,
    FacilityAddition,
    LifeRegistrationSnapshot,
    Membership,
    Organization,
    RuleVersion,
    SubmissionRecord,
    SubmissionSchedule,
    ValidationIssue,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "created_at")
    search_fields = ("name", "code")


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "service_type", "facility_number", "active")
    list_filter = ("service_type", "active", "organization")
    search_fields = ("name", "code", "facility_number")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "facility", "role")
    list_filter = ("role", "facility")
    search_fields = ("user__username", "user__email", "facility__name")


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "external_id",
        "facility",
        "service_start_date",
        "service_end_date",
        "life_registered",
        "active",
    )
    list_filter = ("facility", "life_registered", "active")
    search_fields = ("display_name", "external_id")
    date_hierarchy = "service_start_date"


@admin.register(Addition)
class AdditionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "applies_to_all_active", "active")
    search_fields = ("name", "code")


@admin.register(FacilityAddition)
class FacilityAdditionAdmin(admin.ModelAdmin):
    list_display = ("facility", "addition", "start_date", "end_date", "active")
    list_filter = ("facility", "addition", "active")
    date_hierarchy = "start_date"


@admin.register(ClientAddition)
class ClientAdditionAdmin(admin.ModelAdmin):
    list_display = ("client", "facility_addition", "start_date", "end_date", "anchor_date", "eligible")
    list_filter = ("facility_addition__facility", "facility_addition__addition", "eligible")
    search_fields = ("client__display_name", "client__external_id")


@admin.register(ClientEvent)
class ClientEventAdmin(admin.ModelAdmin):
    list_display = ("client", "event_type", "event_date", "note")
    list_filter = ("event_type", "client__facility")
    search_fields = ("client__display_name", "client__external_id", "note")
    date_hierarchy = "event_date"


@admin.register(RuleVersion)
class RuleVersionAdmin(admin.ModelAdmin):
    list_display = (
        "addition",
        "version",
        "rule_kind",
        "effective_from",
        "effective_to",
        "interval_months",
        "active",
        "approved_at",
    )
    list_filter = ("rule_kind", "active", "addition")
    search_fields = ("addition__name", "version", "source_title", "change_summary")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "effective_from"


@admin.register(SubmissionSchedule)
class SubmissionScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "facility",
        "addition",
        "target_month",
        "submission_kind",
        "due_date",
        "status",
    )
    list_filter = ("facility", "addition", "submission_kind", "status")
    search_fields = ("client__display_name", "client__external_id", "reason")
    date_hierarchy = "due_date"
    readonly_fields = ("computed_at",)


@admin.register(SubmissionRecord)
class SubmissionRecordAdmin(admin.ModelAdmin):
    list_display = ("schedule", "submitted_at", "submitted_by", "source", "accepted")
    list_filter = ("source", "accepted", "schedule__facility")
    date_hierarchy = "submitted_at"


@admin.register(LifeRegistrationSnapshot)
class LifeRegistrationSnapshotAdmin(admin.ModelAdmin):
    list_display = ("facility", "snapshot_date", "registered_count")
    list_filter = ("facility",)
    date_hierarchy = "snapshot_date"


@admin.register(ValidationIssue)
class ValidationIssueAdmin(admin.ModelAdmin):
    list_display = ("facility", "client", "code", "severity", "message", "resolved", "created_at")
    list_filter = ("facility", "severity", "resolved", "code")
    search_fields = ("message", "client__display_name", "client__external_id")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "facility", "user", "action", "object_type", "object_id")
    list_filter = ("action", "facility")
    search_fields = ("object_id", "user__username")
    readonly_fields = (
        "facility",
        "user",
        "action",
        "object_type",
        "object_id",
        "details",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
