from rest_framework import serializers

from logmanage.models import AppOperationLog


class AppOperationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppOperationLog
        fields = [
            'id',
            'created_at',
            'app',
            'category',
            'level',
            'actor',
            'summary',
            'detail',
            'correlation_id',
            'target',
        ]
        read_only_fields = ['id', 'created_at']
