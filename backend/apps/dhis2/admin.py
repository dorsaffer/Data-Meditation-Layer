from django.contrib import admin

from .models import RawDHIS2Record


@admin.register(RawDHIS2Record)
class RawDHIS2RecordAdmin(admin.ModelAdmin):
    list_display = ('dx_name', 'org_unit_name', 'period', 'value', 'fetched_at')
    list_filter = ('dx_name', 'org_unit_name')
    search_fields = ('dx_uid', 'org_unit_uid', 'period')
    readonly_fields = (
        'dx_uid', 'dx_name', 'org_unit_uid', 'org_unit_name', 'period',
        'value', 'raw_payload', 'source_url', 'fetched_at',
    )
