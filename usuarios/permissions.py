from rest_framework.permissions import BasePermission


class EsAdministrador(BasePermission):
    message = "Solo un administrador puede hacer esta acción."

    def has_permission(self, request, view):
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and usuario.rol_nombre == "ADMINISTRADOR")
