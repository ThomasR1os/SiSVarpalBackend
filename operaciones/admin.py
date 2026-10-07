from django.contrib import admin

from operaciones.models import Destino, Evidencia, Notificacion, Posicion, Ruta, RutaDestino


@admin.register(Destino)
class DestinoAdmin(admin.ModelAdmin):
    list_display = ("codigo_externo", "cliente", "fecha", "tipo_servicio", "estado")
    list_filter = ("estado", "tipo_servicio", "fecha")
    search_fields = ("codigo_externo", "nombre_receptor")


@admin.register(Ruta)
class RutaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "fecha", "conductor", "estado", "dentro_de_lima")
    list_filter = ("estado", "fecha")


@admin.register(RutaDestino)
class RutaDestinoAdmin(admin.ModelAdmin):
    list_display = ("ruta", "orden", "destino")


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ("destino", "subido_por", "creado_en")


@admin.register(Posicion)
class PosicionAdmin(admin.ModelAdmin):
    list_display = ("ruta", "latitud", "longitud", "registrado_en")


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "tipo", "leida", "creado_en")
