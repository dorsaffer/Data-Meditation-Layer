from rest_framework import serializers

from .models import DataProduct, DataProductSource, District, Indicator, Observation, QualityCheckResult


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = '__all__'


class IndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indicator
        fields = '__all__'


class ObservationSerializer(serializers.ModelSerializer):
    indicator = IndicatorSerializer(read_only=True)
    district = DistrictSerializer(read_only=True)

    class Meta:
        model = Observation
        fields = '__all__'


class DataProductSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataProductSource
        fields = ('id', 'name', 'description', 'extraction_date', 'reference_period')


class QualityCheckResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityCheckResult
        fields = ('id', 'check_code', 'check_name', 'method', 'severity', 'passed', 'detail', 'checked_at')


class DataProductSerializer(serializers.ModelSerializer):
    indicator = IndicatorSerializer(read_only=True)
    sources = DataProductSourceSerializer(many=True, read_only=True)
    quality_checks = QualityCheckResultSerializer(many=True, read_only=True)

    class Meta:
        model = DataProduct
        fields = '__all__'
