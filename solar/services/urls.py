from django.urls import path, include
from rest_framework.routers import DefaultRouter
import rest_framework_nested.routers as routers

from solar.services.views import (
    ServiceRequestViewSet,
    ServiceAttachmentViewSet,
    ServicePendencyViewSet,
    ServicePaymentDocumentView,
    ServiceAttachmentDownloadView,
    ServiceAttachmentDownloadAllView,
    ServiceTypeViewSet,
    ServiceObservationViewSet,
    ServiceStatusHistoryViewSet,
)

router = DefaultRouter()
router.register(r'services-view', ServiceRequestViewSet, basename='service')
router.register(r'service-types', ServiceTypeViewSet, basename='service-types')
router.register(r'service-observations', ServiceObservationViewSet, basename='service-observations')
router.register(r'service-status-history', ServiceStatusHistoryViewSet, basename='service-status-history')

# Nested Routers para Anexos e Pendências
services_router = routers.NestedSimpleRouter(router, r'services-view', lookup='service')
services_router.register(r'attachments', ServiceAttachmentViewSet, basename='service-attachments')
services_router.register(r'pendencies', ServicePendencyViewSet, basename='service-pendencies')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(services_router.urls)),
    
    # Download individual e ZIP completo
    path('services-view/<int:parent_pk>/attachments/<int:document_pk>/download/', 
         ServiceAttachmentDownloadView.as_view(), 
         name='service-attachment-download'),
         
    path('services-view/<int:parent_pk>/download-all/', 
         ServiceAttachmentDownloadAllView.as_view(), 
         name='service-attachment-download-all'),

    # Documentos de Pagamento
    path('services-view/<int:parent_pk>/payment-document/<str:document_type>/', 
         ServicePaymentDocumentView.as_view(), 
         name='service-payment-document'),
]