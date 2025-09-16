from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

def home_view(request):
    """Simple home view"""
    return render(request, 'home.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', home_view, name='home'),
]
