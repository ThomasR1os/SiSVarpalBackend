from django.contrib import admin

from usuarios.models import Rol, SesionActiva, Usuario


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion")


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("email", "nombre", "apellido", "rol", "cliente", "is_active")
    search_fields = ("email", "nombre", "documento")


@admin.register(SesionActiva)
class SesionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "expira_en", "ip")
