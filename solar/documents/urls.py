from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CompleteProjectViewSet,
)

router = DefaultRouter()
router.register(r'client-projects', CompleteProjectViewSet, basename='clientproject')


urlpatterns = [
    path('', include(router.urls)),
]
