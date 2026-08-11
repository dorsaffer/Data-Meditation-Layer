from rest_framework import serializers

from .models import DataProduct, DataProductSource, District, Indicator, Observation, QualityCheckResult
from .privacy import SMALL_CELL_THRESHOLD, is_small_cell


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = '__all__'


class IndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indicator
        fields = '__all__'


class ObservationSerializer(serializers.ModelSerializer):
    """FR6.7: `value` is small-cell suppressed here, at the one boundary
    every API consumer of Observations goes through - a district×period
    cell below SMALL_CELL_THRESHOLD is generalised to the threshold
    itself (never the true value, never null) so `value` stays a plain
    number and every existing numeric consumer (chart aggregation,
    sorting) keeps working without special-casing a sentinel. is_suppressed
    tells a UI whether the number it received is exact or a generalised
    ceiling, so it can render "< 5" instead of "5".
    """
    indicator = IndicatorSerializer(read_only=True)
    district = DistrictSerializer(read_only=True)
    value = serializers.SerializerMethodField()
    is_suppressed = serializers.SerializerMethodField()

    class Meta:
        model = Observation
        fields = ('id', 'indicator', 'district', 'period', 'value', 'is_suppressed', 'source_raw_record')

    def get_value(self, obs) -> float:
        return SMALL_CELL_THRESHOLD if is_small_cell(obs.value) else obs.value

    def get_is_suppressed(self, obs) -> bool:
        return is_small_cell(obs.value)


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
