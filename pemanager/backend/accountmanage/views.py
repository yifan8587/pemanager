"""账号 / 认证 / API Token 视图。"""
from __future__ import annotations

from django.contrib.auth import update_session_auth_hash
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from accountmanage.models import APIToken, LoginAttempt, User
from accountmanage.permissions import IsAdmin
from accountmanage.serializers import (
    APITokenCreateSerializer,
    APITokenSerializer,
    ChangePasswordSerializer,
    LoginAttemptSerializer,
    PEMTokenObtainPairSerializer,
    UserAdminSerializer,
    UserBriefSerializer,
)


APP_NAME = 'accountmanage'


@api_view(['GET'])
@permission_classes([AllowAny])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


# ---------------- JWT auth ----------------


class LoginView(TokenObtainPairView):
    """POST: {username, password} → {access, refresh, user}"""
    serializer_class = PEMTokenObtainPairSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # 失败也落 LoginAttempt
        try:
            return super().post(request, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            try:
                LoginAttempt.objects.create(
                    username=request.data.get('username') or '',
                    success=False,
                    ip=_ip(request),
                    user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:256],
                    error=str(exc)[:255],
                )
            except Exception:  # noqa: BLE001
                pass
            raise


class MeView(APIView):
    """GET: 当前用户摘要。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserBriefSerializer(request.user).data)


class ChangePasswordView(APIView):
    """POST: 自己改密码。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = ChangePasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        u = request.user
        if not u.check_password(s.validated_data['old_password']):
            return Response({'detail': '当前密码不正确'}, status=status.HTTP_400_BAD_REQUEST)
        u.set_password(s.validated_data['new_password'])
        u.save()
        update_session_auth_hash(request, u)
        return Response({'ok': True})


class LogoutView(APIView):
    """POST: 退出（前端清除本地令牌；后端不维护黑名单则仅返回 OK）。"""

    permission_classes = [IsAuthenticated]

    def post(self, _request):
        # simplejwt 黑名单默认未启用；前端只需丢弃 access/refresh 即可
        return Response({'ok': True})


# ---------------- 用户管理（admin） ----------------


class UserViewSet(viewsets.ModelViewSet):
    """admin: 用户 CRUD。"""

    queryset = User.objects.select_related('customer').all().order_by('username')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get('role'):
            qs = qs.filter(role=p['role'])
        if p.get('customer_code'):
            qs = qs.filter(customer__code=p['customer_code'])
        if p.get('search'):
            from django.db.models import Q
            q = p['search']
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q))
        return qs

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        new_pwd = (request.data or {}).get('new_password') or ''
        if len(new_pwd) < 8:
            return Response({'detail': '密码至少 8 位'}, status=status.HTTP_400_BAD_REQUEST)
        u = self.get_object()
        u.set_password(new_pwd)
        u.save()
        return Response({'ok': True})

    @action(detail=True, methods=['post'], url_path='disable')
    def disable(self, _request, pk=None):
        u = self.get_object()
        u.is_active = False
        u.save(update_fields=['is_active'])
        return Response({'ok': True, 'is_active': u.is_active})

    @action(detail=True, methods=['post'], url_path='enable')
    def enable(self, _request, pk=None):
        u = self.get_object()
        u.is_active = True
        u.save(update_fields=['is_active'])
        return Response({'ok': True, 'is_active': u.is_active})


# ---------------- API Token ----------------


class APITokenViewSet(viewsets.ModelViewSet):
    """
    admin: 可管理任意用户的 token；非 admin：只能管理自己的。
    创建后明文密钥只在响应里 `plaintext` 字段中返回一次。
    """

    serializer_class = APITokenSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        u = self.request.user
        qs = APIToken.objects.select_related('user').all()
        if not getattr(u, 'is_admin_role', False):
            qs = qs.filter(user=u)
        p = self.request.query_params
        if p.get('username'):
            qs = qs.filter(user__username=p['username'])
        if p.get('revoked') in ('0', '1'):
            qs = qs.filter(revoked=p['revoked'] == '1')
        return qs.order_by('-created_at')

    def create(self, request, *args, **kwargs):
        s = APITokenCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        # 非 admin 只能给自己创建
        u = request.user
        target = s.validated_data.get('user') or u
        if not getattr(u, 'is_admin_role', False) and target.pk != u.pk:
            return Response({'detail': '只能为自己创建 API Token'}, status=status.HTTP_403_FORBIDDEN)
        tok, plaintext = APIToken.generate(
            target,
            name=s.validated_data['name'],
            ttl_days=s.validated_data.get('ttl_days') or None,
        )
        data = APITokenSerializer(tok).data
        data['plaintext'] = plaintext
        data['warning'] = '此明文仅本次显示一次，请立即妥善保存。后续无法再获取，丢失请重新生成。'
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        # 软吊销而不是真删，便于审计
        instance.revoked = True
        instance.save(update_fields=['revoked'])

    @action(detail=True, methods=['post'], url_path='revoke')
    def revoke(self, _request, pk=None):
        tok = self.get_object()
        tok.revoked = True
        tok.save(update_fields=['revoked'])
        return Response({'ok': True})


# ---------------- 登录尝试（admin 可查） ----------------


class LoginAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LoginAttempt.objects.all().order_by('-created_at')
    serializer_class = LoginAttemptSerializer
    permission_classes = [IsAuthenticated, IsAdmin]


# ---------------- 工具 ----------------


def _ip(request):
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None
