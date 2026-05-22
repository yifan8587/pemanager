from rest_framework import serializers

from qosmanage.models import QoSPolicy, QoSRule


class QoSRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = QoSRule
        fields = [
            'id',
            'policy',
            'class_id',
            'rate_mbps',
            'ceil_mbps',
            'priority',
            'match_kind',
            'match_value',
            'remark',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        obj = QoSRule(**validated_data)
        obj.full_clean()
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.full_clean()
        instance.save()
        return instance


class QoSPolicySerializer(serializers.ModelSerializer):
    rules = QoSRuleSerializer(many=True, read_only=True)

    class Meta:
        model = QoSPolicy
        fields = [
            'id',
            'name',
            'interface_name',
            'direction',
            'root_kind',
            'default_rate_mbps',
            'default_ceil_mbps',
            'enabled',
            'remark',
            'rules',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'rules', 'created_at', 'updated_at']

    def create(self, validated_data):
        obj = QoSPolicy(**validated_data)
        obj.full_clean()
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.full_clean()
        instance.save()
        return instance
