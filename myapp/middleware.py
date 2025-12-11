import logging

logger = logging.getLogger(__name__)


class DisableCSRFForAPIMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            setattr(request, '_dont_enforce_csrf_checks', True)
        
        response = self.get_response(request)
        return response


class AuthDebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            logger.info(f"API Request: {request.method} {request.path}")
            logger.info(f"Auth Header: {request.META.get('HTTP_AUTHORIZATION', 'None')}")
            logger.info(f"User: {request.user}")
            logger.info(f"Is Authenticated: {request.user.is_authenticated}")
        
        response = self.get_response(request)
        
        if request.path.startswith('/api/') and response.status_code in [401, 403]:
            logger.warning(f"Auth failed: {response.status_code} for {request.path}")
        
        return response