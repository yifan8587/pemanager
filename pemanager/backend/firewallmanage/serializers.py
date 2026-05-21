from rest_framework import serializers

from firewallmanage.models import FirewallRule


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
