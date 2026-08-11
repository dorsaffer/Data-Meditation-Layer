from rest_framework import serializers

from .models import FHIRValidationResult


class FHIRValidationResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = FHIRValidationResult
        fields = '__all__'
