"""自定义认证：
- `APITokenAuthentication`：识别 Authorization: Bearer pem_<prefix>.<secret> 或 X-API-Key 头。
- JWT 由 `rest_framework_simplejwt.authentication.JWTAuthentication` 直接承担（在 settings 中先放它）。

注意：simplejwt 的 JWTAuthentication 也读 `Authorization: Bearer ...`，但 JWT 不以 `pem_` 开头；
本类放在 DRF DEFAULT_AUTHENTICATION_CLASSES 中 JWTAuthentication 之后，看到非 JWT 的 `pem_*` 才接管。
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import authentication, exceptions

from accountmanage.models import APIToken


def _client_ip(request) -> str | None:
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


class APITokenAuthentication(authentication.BaseAuthentication):
    keyword = 'Bearer'

    def authenticate(self, request):
        token_str = self._extract_token(request)
        if not token_str:
            return None
        if not token_str.startswith('pem_'):
            return None  # 让别的认证器接管（JWT 等）

        try:
            prefix, secret = token_str.split('.', 1)
        except ValueError:
            raise exceptions.AuthenticationFailed('API Token 格式应为 prefix.secret')

        try:
            tok = APIToken.objects.select_related('user').get(prefix=prefix)
        except APIToken.DoesNotExist:
            raise exceptions.AuthenticationFailed('API Token 无效')

        if tok.revoked:
            raise exceptions.AuthenticationFailed('API Token 已吊销')
        if tok.is_expired:
            raise exceptions.AuthenticationFailed('API Token 已过期')
        if not tok.verify_secret(secret):
            raise exceptions.AuthenticationFailed('API Token 密钥不匹配')
        if not tok.user.is_active:
            raise exceptions.AuthenticationFailed('用户已禁用')

        try:
            tok.mark_used(_client_ip(request))
        except Exception:  # noqa: BLE001
            pass

        # 把令牌挂回 request 便于审计 / 后续判断 scope
        request._api_token = tok
        return (tok.user, tok)

    @staticmethod
    def _extract_token(request) -> str | None:
        auth = request.META.get('HTTP_AUTHORIZATION', '') or ''
        if auth:
            parts = auth.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                return parts[1]
        xkey = request.META.get('HTTP_X_API_KEY')
        if xkey:
            return xkey.strip()
        return None
