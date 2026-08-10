from rest_framework import serializers

from .models import DataProduct, District, Indicator, Observation


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


class DataProductSerializer(serializers.ModelSerializer):
    indicator = IndicatorSerializer(read_only=True)

    class Meta:
        model = DataProduct
        fields = '__all__'
