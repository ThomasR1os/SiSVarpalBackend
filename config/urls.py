from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from catalogos.views import (
    ClienteViewSet,
    EmpresaView,
    GeocercaView,
    MotivoViewSet,
    PlantillaImportacionViewSet,
    PuntoViewSet,
    VehiculoViewSet,
)
from operaciones.views import DestinoViewSet, MapaRutasView, NotificacionViewSet, RutaViewSet
from usuarios.views import LoginView, LogoutView, MeView, RefreshView, UsuarioViewSet

router = DefaultRouter()
router.register("usuarios", UsuarioViewSet, basename="usuario")
router.register("clientes", ClienteViewSet, basename="cliente")
router.register("puntos", PuntoViewSet, basename="punto")
router.register("vehiculos", VehiculoViewSet, basename="vehiculo")
router.register("motivos", MotivoViewSet, basename="motivo")
router.register("plantillas", PlantillaImportacionViewSet, basename="plantilla")
router.register("destinos", DestinoViewSet, basename="destino")
router.register("rutas", RutaViewSet, basename="ruta")
router.register("notificaciones", NotificacionViewSet, basename="notificacion")

admin.site.site_header = "SiSVarpal"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/refresh/", RefreshView.as_view(), name="refresh"),
    path("api/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/empresa/", EmpresaView.as_view(), name="empresa"),
    path("api/geocerca/", GeocercaView.as_view(), name="geocerca"),
    path("api/mapa/rutas/", MapaRutasView.as_view(), name="mapa-rutas"),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
