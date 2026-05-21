"""全局视图（CSRF 引导等）。"""

from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def csrf_bootstrap(_request):
    """GET：下发 csrftoken Cookie，供浏览器跨页 POST 时携带 X-CSRFToken。"""
    return JsonResponse({'detail': 'ok'})
