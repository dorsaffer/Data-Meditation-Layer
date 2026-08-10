from rest_framework import serializers

from .models import RawDHIS2Record


class RawDHIS2RecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawDHIS2Record
        fields = '__all__'
