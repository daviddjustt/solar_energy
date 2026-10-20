from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

# Importe os ViewSets recém-criados
from solar.services.views import ServiceTypeViewSet, ServiceRequestViewSet, ExternalUserViewSet

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

# Registe as rotas dos serviços
router.register("service-types", ServiceTypeViewSet, basename="service-type")
router.register("services-view", ServiceRequestViewSet, basename="service")
router.register("external-users", ExternalUserViewSet, basename="external-user")


app_name = "services"
urlpatterns = router.urls