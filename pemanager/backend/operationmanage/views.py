from rest_framework.decorators import api_view
from rest_framework.response import Response

APP_NAME = "operationmanage"

@api_view(["GET"])
def health(_request):
    return Response({"app": APP_NAME, "status": "ok"})
