from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.dashboard, name="dashboard"),
    path("guide/", views.usage_guide, name="usage_guide"),
    path("deployment-check/", views.deployment_check, name="deployment_check"),
    path("schedules/", views.schedule_list, name="schedule_list"),
    path("clients/", views.client_list, name="client_list"),
    path("recalculate/", views.recalculate, name="recalculate"),
    path("schedules/<int:schedule_id>/submitted/", views.mark_submitted, name="mark_submitted"),
    path("schedules/submitted/bulk/", views.bulk_mark_submitted, name="bulk_mark_submitted"),
    path("imports/submission-records.csv", views.import_submission_records_csv, name="import_submission_records_csv"),
    path("imports/submission-records-template.csv", views.submission_import_template_csv, name="submission_import_template_csv"),
    path("exports/schedules.csv", views.export_schedules_csv, name="export_schedules_csv"),
]
