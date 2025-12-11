from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from django.http import JsonResponse
from myapp import views
import django.utils.timezone as timezone
from django.shortcuts import redirect


def api_home(request):
    """API home endpoint"""
    return JsonResponse({
        'message': 'Telerad PACS API Server',
        'version': '1.0',
        'status': 'running',
        'endpoints': {
            'receive_dicom': '/api/dicom/receive/',
            'get_studies': '/api/studies/',
            'get_study_images': '/api/studies/<id>/images/',
            'get_stats': '/api/stats/',
            'api_info': '/api/info/',
            'admin': '/admin/'
        }
    })

def health_check(request):
    """Health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'message': 'API is running',
        'timestamp': timezone.now().isoformat()
    })

def home_redirect(request):
    """Redirect to static index.html"""
    return redirect('/static/index.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('myapp.urls')),
    path('dicom/<path:filename>/', views.serve_dicom, name='serve_dicom'),
    # path('', api_home, name='api_home'),
    path('health/', health_check, name='health_check'),
    # path('index/', views.index, name='index'),
    path('api-info/', api_home, name='api_home'), 
    path('', home_redirect, name='home'),
    
]


if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)