from rest_framework.authentication import BaseAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from usuarios.models import SesionActiva, Usuario


class JWTSesionUnicaAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        usuario = super().get_user(validated_token)
        sid = validated_token.get("sid")
        sesion = SesionActiva.objects.filter(usuario_id=usuario.id).only("refresh_jti").first()
        if not sid or sesion is None or sesion.refresh_jti != sid:
            raise InvalidToken("La sesión ya no es válida porque se inició sesión en otro lugar.")
        if not usuario.is_active:
            raise InvalidToken("El usuario está inactivo.")
        return Usuario.objects.select_related("rol", "cliente").get(pk=usuario.pk)


class AutenticacionAbierta(BaseAuthentication):
    """No lee el access token. Permite que login y refresh respondan 401."""

    def authenticate(self, request):
        return None

    def authenticate_header(self, request):
        return "Bearer"

