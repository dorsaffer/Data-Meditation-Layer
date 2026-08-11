from django.contrib import admin

from .models import AuditEvent, ProvenanceRecord


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Read-only: no add/change/delete permission, mirroring the model's
    own save()/delete() guards (see models.py) - the admin form must not
    offer a UI path around the append-only rule.
    """
    list_display = ('timestamp', 'actor', 'organisation', 'action', 'resource_type', 'resource_id', 'outcome')
    list_filter = ('action', 'outcome')
    search_fields = ('actor', 'organisation', 'resource_type', 'resource_id', 'correlation_id')
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProvenanceRecord)
class ProvenanceRecordAdmin(admin.ModelAdmin):
    list_display = ('occurred_at', 'activity', 'data_product', 'resource_type', 'resource_id', 'performed_by')
    list_filter = ('activity',)
    search_fields = ('resource_type', 'resource_id', 'description', 'correlation_id')
    date_hierarchy = 'occurred_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
