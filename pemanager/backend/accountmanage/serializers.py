"""账号 / Token serializers。"""
from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accountmanage.models import APIToken, LoginAttempt, User
from resourcemanage.models import ResourceCustomer


# ----------------- 用户 -----------------


class UserBriefSerializer(serializers.ModelSerializer):
    """登录 / me 返回的瘦身用户信息。"""

    customer_code = serializers.CharField(source='customer.code', read_only=True, default=None)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    is_admin = serializers.BooleanField(source='is_admin_role', read_only=True)
    is_operator = serializers.BooleanField(source='is_operator_role', read_only=True)
    is_customer = serializers.BooleanField(source='is_customer_role', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone', 'remark',
            'customer', 'customer_code', 'customer_name',
            'is_active', 'is_superuser', 'is_staff',
            'is_admin', 'is_operator', 'is_customer',
            'last_login', 'date_joined',
        ]
        read_only_fields = ['is_superuser', 'is_staff', 'last_login', 'date_joined']


class UserAdminSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    customer_code = serializers.SlugRelatedField(
        source='customer',
        slug_field='code',
        queryset=ResourceCustomer.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone', 'remark',
            'customer', 'customer_code',
            'is_active', 'is_superuser', 'is_staff',
            'last_login', 'date_joined',
            'password',
        ]
        read_only_fields = ['last_login', 'date_joined']

    def validate(self, attrs):
        role = attrs.get('role') or getattr(self.instance, 'role', None)
        customer = attrs.get('customer', getattr(self.instance, 'customer', None))
        if role == User.Role.CUSTOMER and not customer:
            raise serializers.ValidationError({'customer_code': '客户账号必须绑定客户'})
        # 新建必须有密码
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': '新建用户必须设置密码'})
        if attrs.get('password'):
            try:
                validate_password(attrs['password'])
            except DjValidationError as exc:
                raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs

    def create(self, validated):
        pwd = validated.pop('password', None)
        user = User(**validated)
        if pwd:
            user.set_password(pwd)
        user.save()
        return user

    def update(self, instance, validated):
        pwd = validated.pop('password', None)
        for k, v in validated.items():
            setattr(instance, k, v)
        if pwd:
            instance.set_password(pwd)
        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, v):
        try:
            validate_password(v)
        except DjValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return v


# ----------------- JWT -----------------


class PEMTokenObtainPairSerializer(TokenObtainPairSerializer):
    """登录响应额外带上 user 摘要，便于前端一次拿全。"""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['username'] = user.username
        token['customer_code'] = user.customer.code if user.customer else None
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserBriefSerializer(self.user).data
        # 登录成功审计
        request = self.context.get('request')
        try:
            LoginAttempt.objects.create(
                username=attrs.get('username') or '',
                success=True,
                ip=_get_ip(request),
                user_agent=_get_ua(request),
            )
        except Exception:  # noqa: BLE001
            pass
        return data


def _get_ip(request):
    if not request:
        return None
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _get_ua(request):
    if not request:
        return ''
    return (request.META.get('HTTP_USER_AGENT') or '')[:256]


# ----------------- API Token -----------------


class APITokenSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = APIToken
        fields = [
            'id', 'user', 'user_username', 'name', 'prefix',
            'scope', 'expires_at', 'revoked', 'is_expired',
            'last_used_at', 'last_used_ip', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'prefix', 'last_used_at', 'last_used_ip',
            'created_at', 'updated_at',
        ]


class APITokenCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    ttl_days = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=3650)
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True
    )


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = ['id', 'username', 'success', 'ip', 'user_agent', 'error', 'created_at']
