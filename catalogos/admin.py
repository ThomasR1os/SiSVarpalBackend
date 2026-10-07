from django.contrib import admin

from catalogos.models import Cliente, Empresa, Geocerca, Motivo, PlantillaImportacion, Punto, Vehiculo


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("razon_social", "ruc")


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("ruc", "razon_social", "activo")
    search_fields = ("ruc", "razon_social")


@admin.register(Punto)
class PuntoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "cliente", "es_principal", "es_base_origen", "es_sede", "es_base_final")


@admin.register(Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    list_display = ("placa", "marca", "modelo", "activo")


@admin.register(Motivo)
class MotivoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descripcion", "aplica_a", "activo")


@admin.register(Geocerca)
class GeocercaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activa")


@admin.register(PlantillaImportacion)
class PlantillaAdmin(admin.ModelAdmin):
    list_display = ("cliente", "tipo", "nombre", "activa")
