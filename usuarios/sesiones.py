from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import AuthenticationFailed

from usuarios.models import SesionActiva, Usuario


def emitir_tokens(usuario):
    refresh = RefreshToken.for_user(usuario)
    jti = str(refresh["jti"])
    refresh["sid"] = jti
    access = refresh.access_token
    access["sid"] = jti
    return str(access), str(refresh), jti


def _ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    if not ip or len(ip) > 45:
        return None
    return ip


def iniciar_sesion(usuario, request):
    access, refresh, jti = emitir_tokens(usuario)
    SesionActiva.objects.update_or_create(
        usuario=usuario,
        defaults={
            "refresh_jti": jti,
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            "ip": _ip(request),
            "expira_en": timezone.now() + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"],
        },
    )
    return access, refresh


def rotar_sesion(refresh_crudo):
    try:
        token = RefreshToken(refresh_crudo)
    except TokenError as exc:
        raise AuthenticationFailed("El refresh token no es válido.") from exc
    usuario = Usuario.objects.select_related("rol", "cliente").filter(pk=token["user_id"], is_active=True).first()
    if usuario is None:
        raise AuthenticationFailed("El usuario no puede iniciar sesión.")
    sesion = SesionActiva.objects.filter(usuario=usuario).first()
    if sesion is None or sesion.refresh_jti != str(token["jti"]) or not sesion.refresh_jti:
        raise AuthenticationFailed("La sesión ya no es válida porque se inició sesión en otro lugar.")
    if sesion.expira_en <= timezone.now():
        raise AuthenticationFailed("La sesión expiró. Vuelva a iniciar sesión.")
    access, refresh, jti = emitir_tokens(usuario)
    sesion.refresh_jti = jti
    sesion.expira_en = timezone.now() + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    sesion.save(update_fields=["refresh_jti", "expira_en"])
    return access, refresh


def cerrar_sesion(usuario):
    SesionActiva.objects.filter(usuario=usuario).update(refresh_jti="", expira_en=timezone.now())


def autenticar(request, email, password):
    correo = (email or "").strip().lower()
    candidato = Usuario.objects.filter(email=correo).first()
    if candidato is None:
        raise AuthenticationFailed("Credenciales incorrectas.")
    usuario = authenticate(request, username=candidato.username, password=password)
    if usuario is None or not usuario.is_active:
        raise AuthenticationFailed("Credenciales incorrectas.")
    return Usuario.objects.select_related("rol", "cliente").get(pk=usuario.pk)
