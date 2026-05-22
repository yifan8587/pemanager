from rest_framework import serializers

from firewallmanage.models import FirewallRule, FirewallSettings, NATRule


class FirewallRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FirewallRule
        fields = [
            'id',
            'name',
            'enabled',
            'chain',
            'action',
            'family',
            'protocol',
            'src_cidr',
            'dst_cidr',
            'src_port',
            'dst_port',
            'in_interface',
            'out_interface',
            'priority',
            'remark',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        obj = FirewallRule(**validated_data)
        obj.full_clean()
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.full_clean()
        instance.save()
        return instance


class NATRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NATRule
        fields = [
            'id',
            'name',
            'enabled',
            'kind',
            'family',
            'protocol',
            'in_interface',
            'out_interface',
            'src_cidr',
            'dst_cidr',
            'dst_port',
            'to_ip',
            'to_port',
            'priority',
            'remark',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        obj = NATRule(**validated_data)
        obj.full_clean()
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.full_clean()
        instance.save()
        return instance


class FirewallSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FirewallSettings
        fields = [
            'id',
            'engine',
            'policy_input',
            'policy_output',
            'policy_forward',
            'last_apply_at',
            'last_apply_ok',
            'last_apply_summary',
            'updated_at',
        ]
        read_only_fields = ['id', 'last_apply_at', 'last_apply_ok', 'last_apply_summary', 'updated_at']
