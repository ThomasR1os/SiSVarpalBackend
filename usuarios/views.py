import django_filters
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from usuarios.authentication import AutenticacionAbierta
from usuarios.models import Usuario
from usuarios.permissions import EsAdministrador
from usuarios.serializers import UsuarioSerializer
from usuarios.sesiones import autenticar, cerrar_sesion, iniciar_sesion, rotar_sesion


class UsuarioFilter(django_filters.FilterSet):
    rol = django_filters.CharFilter(field_name="rol__nombre")

    class Meta:
        model = Usuario
        fields = ["rol", "cliente", "is_active"]


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [AutenticacionAbierta]

    def post(self, request):
        email = request.data.get("email", "")
        password = request.data.get("password", "")
        if not email or not password:
            raise ValidationError({"email": ["Indique correo y clave."]})
        usuario = autenticar(request, email, password)
        access, refresh = iniciar_sesion(usuario, request)
        return Response(
            {
                "access": access,
                "refresh": refresh,
                "user": UsuarioSerializer(usuario).data,
            }
        )


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [AutenticacionAbierta]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            raise ValidationError({"refresh": ["El refresh token es obligatorio."]})
        access, refresh_nuevo = rotar_sesion(refresh)
        return Response({"access": access, "refresh": refresh_nuevo})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cerrar_sesion(request.user)
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)


class UsuarioViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated, EsAdministrador]
    queryset = Usuario.objects.select_related("rol", "cliente").order_by("id")
    filterset_class = UsuarioFilter
    search_fields = ["email", "nombre", "apellido", "documento"]
    ordering_fields = ["id", "email", "nombre"]

    def get_queryset(self):
        return self.queryset

    def destroy(self, request, *args, **kwargs):
        usuario = self.get_object()
        if usuario.pk == request.user.pk:
            raise ValidationError({"detail": "No puede desactivar su propio usuario."})
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        cerrar_sesion(usuario)
        return Response(status=204)
