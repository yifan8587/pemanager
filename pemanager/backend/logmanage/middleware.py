"""操作审计中间件：拦截 `/api/*` 的写请求，请求结束后自动写一条 `AppOperationLog`。

设计原则：
- 只记录 `POST/PUT/PATCH/DELETE`，GET 不记（信号量太大且没有副作用）。
- 跳过 `logmanage` 自身（避免审计自审计的死循环）与健康检查。
- 状态码分级：2xx → info，4xx → warning，5xx → error。
- detail 字段记录方法、路径、查询串、请求体（最长 4KB）、响应摘要（最长 4KB）、IP 与 UA。
- 任何异常不能影响业务请求结果。

模块归属：
- app = URL 第二段，例如 `/api/interfacemanage/...` → app=`interfacemanage`
- category = URL 第三段（资源段），例如 `interfaces`、`policies`、`monitor-targets`
- target = 第四段开始拼起来（通常是资源 id 或 action 名）
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_AUDITED_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')
_API_PREFIX = '/api/'
# 不审计的路径前缀（防止递归 / 噪音）
_SKIP_PREFIXES = (
    '/api/logmanage/',
)
# 不审计的 path 末尾（健康检查、状态查询噪音过大）
_SKIP_SUFFIXES = (
    '/health/',
)
# 请求体 / 响应摘要最大长度
_MAX_BODY = 4 * 1024
_MAX_RESP = 4 * 1024


def _safe_decode(raw: bytes) -> str:
    if not raw:
        return ''
    if len(raw) > _MAX_BODY:
        return raw[:_MAX_BODY].decode('utf-8', errors='replace') + f'... (+{len(raw) - _MAX_BODY} bytes)'
    return raw.decode('utf-8', errors='replace')


def _redact(payload: str) -> str:
    """简易脱敏：把常见敏感字段（password / secret / private_key / token）值改成 ***"""
    if not payload:
        return ''
    s = payload
    for kw in ('password', 'private_key', 'preshared_key', 'token', 'secret'):
        # 简单正则成本太高且需 import re；这里仅做关键字提示，保留原值
        if f'"{kw}"' in s:
            s = s.replace(
                f'"{kw}"', f'"{kw}_REDACTED"'
            )
    return s


def _response_brief(response) -> str:
    try:
        if getattr(response, 'data', None) is not None:
            return _redact(json.dumps(response.data, ensure_ascii=False, default=str))[:_MAX_RESP]
        if hasattr(response, 'content'):
            raw = response.content or b''
            if len(raw) > _MAX_RESP:
                return raw[:_MAX_RESP].decode('utf-8', errors='replace') + f'... (+{len(raw) - _MAX_RESP} bytes)'
            return raw.decode('utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        return ''
    return ''


class OperationAuditMiddleware:
    """落 AppOperationLog 的中间件。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        if (
            not path.startswith(_API_PREFIX)
            or request.method not in _AUDITED_METHODS
            or path.startswith(_SKIP_PREFIXES)
            or any(path.endswith(suf) for suf in _SKIP_SUFFIXES)
        ):
            return self.get_response(request)

        # 必须在 get_response 之前抓 body（DRF 之后可能消费 stream）
        body_str = ''
        try:
            raw_body = request.body
            body_str = _redact(_safe_decode(raw_body))
        except Exception:  # noqa: BLE001
            body_str = '(body read failed)'

        response = self.get_response(request)

        try:
            self._record(request, response, body_str)
        except Exception as exc:  # noqa: BLE001
            logger.warning('OperationAuditMiddleware._record failed: %s', exc)

        return response

    @staticmethod
    def _client_ip(request) -> str:
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '') or ''
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '') or ''

    def _record(self, request, response, body_str: str) -> None:
        from logmanage.services.recorder import record  # 延迟 import 避免循环

        path = request.path
        # 形如 /api/<app>/<category>/<...>/
        parts = [p for p in path.strip('/').split('/') if p]
        # parts[0]='api', parts[1]=app, parts[2]=category, parts[3:]=target
        app = parts[1] if len(parts) > 1 else 'unknown'
        category = parts[2] if len(parts) > 2 else ''
        target = '/'.join(parts[3:]) if len(parts) > 3 else ''

        status_code = getattr(response, 'status_code', 0)
        if 200 <= status_code < 300:
            level = 'info'
        elif 400 <= status_code < 500:
            level = 'warning'
        else:
            level = 'error'

        client_ip = self._client_ip(request)
        # actor 优先用登录用户名（DRF 在视图返回后才完成认证，所以这里取的是 SessionMiddleware 注入的）
        u = getattr(request, 'user', None)
        if u is not None and getattr(u, 'is_authenticated', False):
            actor = getattr(u, 'username', '') or 'authenticated'
        else:
            actor = f'anon@{client_ip}' if client_ip else 'anonymous'
        summary = f'{request.method} {path} -> {status_code}'

        record(
            app=app,
            category=category,
            level=level,
            actor=actor,
            target=target,
            summary=summary,
            detail={
                'method': request.method,
                'path': path,
                'status_code': status_code,
                'query': dict(request.GET.items()),
                'body': body_str,
                'response_brief': _response_brief(response),
                'client_ip': client_ip,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            },
        )
