from rest_framework import serializers

from .models import AuditEvent, ProvenanceRecord


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = (
            'id', 'actor', 'organisation', 'action', 'resource_type', 'resource_id',
            'outcome', 'correlation_id', 'detail', 'timestamp',
        )


class ProvenanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProvenanceRecord
        fields = (
            'id', 'data_product', 'resource_type', 'resource_id', 'activity', 'description',
            'source_reference', 'performed_by', 'correlation_id', 'occurred_at',
        )
