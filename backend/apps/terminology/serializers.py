from rest_framework import serializers

from .models import TerminologyMapping


class TerminologyMappingSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(source='reviewer.username', read_only=True, default=None)

    class Meta:
        model = TerminologyMapping
        fields = '__all__'
