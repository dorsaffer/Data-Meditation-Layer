from rest_framework import serializers

from apps.data_products.serializers import DistrictSerializer

from .models import DistrictPopulation, PopulationDataQualityIssue


class DistrictPopulationSerializer(serializers.ModelSerializer):
    district = DistrictSerializer(read_only=True)

    class Meta:
        model = DistrictPopulation
        fields = '__all__'


class PopulationDataQualityIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = PopulationDataQualityIssue
        fields = '__all__'
