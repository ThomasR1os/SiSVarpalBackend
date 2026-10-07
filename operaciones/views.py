import django_filters
from django.db.models import ProtectedError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalogos.serializers import PuntoBreveSerializer
from config.coordenadas import coordenada_texto
from operaciones.models import Destino, Notificacion, Ruta
from operaciones.plantillas_excel import plantilla_destinos, plantilla_rutas
from operaciones.serializers import (
    CierreSerializer,
    DestinoSerializer,
    DestinoWriteSerializer,
    EvidenciaSerializer,
    NotificacionSerializer,
    OptimizarSerializer,
    OrdenSerializer,
    PosicionSerializer,
    ReprogramarSerializer,
    RutaSerializer,
    RutaWriteSerializer,
)
from operaciones.services.destinos import cerrar_destino, reprogramar_destino
from operaciones.services.importacion import importar_destinos, importar_rutas
from operaciones.services.rutas import (
    aplicar_orden,
    cancelar_ruta,
    confirmar_llegada,
    confirmar_ruta,
    destinos_visibles,
    iniciar_ruta,
    proponer_ruta,
    puntos_de_mapa,
    puede_operar_parada,
    registrar_posicion,
    rutas_visibles,
    seguimiento_activo_para,
)
from usuarios.models import Rol
from usuarios.permissions import EsAdministrador


class DestinoFilter(django_filters.FilterSet):
    sin_ruta = django_filters.BooleanFilter(method="filtrar_sin_ruta")

    class Meta:
        model = Destino
        fields = ["cliente", "fecha", "estado", "tipo_servicio"]

    def filtrar_sin_ruta(self, queryset, name, value):
        if value:
            return queryset.filter(asignacion__isnull=True)
        return queryset.filter(asignacion__isnull=False)


class DestinoViewSet(viewsets.ModelViewSet):
    filterset_class = DestinoFilter
    search_fields = ["codigo_externo", "nombre_receptor", "apellido_receptor", "direccion"]
    ordering_fields = ["fecha", "id", "codigo_externo"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy", "reprogramar", "importar", "plantilla"}:
            return [IsAuthenticated(), EsAdministrador()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return destinos_visibles(self.request.user)

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return DestinoWriteSerializer
        return DestinoSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        destino = serializer.save()
        return Response(DestinoSerializer(destino).data, status=201)

    def update(self, request, *args, **kwargs):
        destino = self.get_object()
        serializer = self.get_serializer(destino, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        destino = serializer.save()
        return Response(DestinoSerializer(destino).data)

    def destroy(self, request, *args, **kwargs):
        destino = self.get_object()
        if destino.estado != Destino.Estado.NO_INICIADO or hasattr(destino, "asignacion"):
            raise ValidationError({"detail": "Solo se elimina un destino que no ha iniciado y no está en una ruta."})
        try:
            destino.delete()
        except ProtectedError as exc:
            raise ValidationError({"detail": "El destino está en uso."}) from exc
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def reprogramar(self, request, pk=None):
        destino = self.get_object()
        serializer = ReprogramarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        destino = reprogramar_destino(destino, serializer.validated_data["fecha"])
        return Response(DestinoSerializer(destino).data)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def cerrar(self, request, pk=None):
        destino = self.get_object()
        if not puede_operar_parada(request.user, destino):
            raise PermissionDenied("No puede cerrar este destino.")
        serializer = CierreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        destino = cerrar_destino(
            destino=destino,
            resultado=serializer.validated_data["resultado"],
            motivo=serializer.validated_data.get("motivo"),
            observacion=serializer.validated_data.get("observacion", ""),
            fotos=request.FILES.getlist("fotos"),
            usuario=request.user,
        )
        return Response(DestinoSerializer(destino).data)

    @action(detail=True, methods=["get"])
    def evidencias(self, request, pk=None):
        destino = self.get_object()
        if request.user.rol_nombre != Rol.Nombre.ADMINISTRADOR and not puede_operar_parada(request.user, destino):
            if request.user.rol_nombre != Rol.Nombre.CLIENTE:
                raise PermissionDenied("No puede ver estas evidencias.")
        return Response(EvidenciaSerializer(destino.evidencias.all(), many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"])
    def plantilla(self, request):
        return plantilla_destinos()

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def importar(self, request):
        archivo = request.FILES.get("archivo")
        cliente_id = request.data.get("cliente_id")
        if archivo is None:
            raise ValidationError({"archivo": ["Adjunte el Excel."]})
        from catalogos.models import Cliente

        cliente = Cliente.objects.filter(pk=cliente_id, activo=True).first()
        if cliente is None:
            raise ValidationError({"cliente_id": ["Indique un cliente activo."]})
        resultado = importar_destinos(cliente=cliente, archivo=archivo, usuario=request.user)
        return Response(resultado)


class RutaFilter(django_filters.FilterSet):
    class Meta:
        model = Ruta
        fields = ["cliente", "fecha", "estado", "conductor", "vehiculo"]


class RutaViewSet(viewsets.ModelViewSet):
    filterset_class = RutaFilter
    ordering_fields = ["fecha", "id", "estado"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in {
            "create",
            "partial_update",
            "update",
            "confirmar",
            "cancelar",
            "orden",
            "optimizar",
            "importar",
            "plantilla",
        }:
            return [IsAuthenticated(), EsAdministrador()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return rutas_visibles(self.request.user)

    def get_serializer_class(self):
        if self.action in {"create", "partial_update", "update"}:
            return RutaWriteSerializer
        return RutaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ruta = serializer.save()
        return Response(self._leer(ruta), status=201)

    def partial_update(self, request, *args, **kwargs):
        ruta = self.get_object()
        serializer = self.get_serializer(ruta, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ruta = serializer.save()
        return Response(self._leer(ruta))

    def _leer(self, ruta):
        ruta = rutas_visibles(self.request.user).get(pk=ruta.pk)
        return RutaSerializer(ruta, context={"request": self.request}).data

    @action(detail=False, methods=["post"])
    def optimizar(self, request):
        serializer = OptimizarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        return Response(
            proponer_ruta(
                cliente=datos["cliente"],
                fecha=datos["fecha"],
                base_origen=datos.get("base_origen"),
                base_final=datos.get("base_final"),
                destinos=datos["destinos"],
            )
        )

    @action(detail=True, methods=["post"])
    def confirmar(self, request, pk=None):
        ruta = confirmar_ruta(self.get_object())
        return Response(self._leer(ruta))

    @action(detail=True, methods=["post"])
    def iniciar(self, request, pk=None):
        ruta = iniciar_ruta(self.get_object(), request.user)
        return Response(self._leer(ruta))

    @action(detail=True, methods=["post"], url_path="llegada-base")
    def llegada_base(self, request, pk=None):
        ruta = confirmar_llegada(self.get_object(), request.user)
        return Response(self._leer(ruta))

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        ruta = cancelar_ruta(self.get_object())
        return Response(self._leer(ruta))

    @action(detail=True, methods=["patch"])
    def orden(self, request, pk=None):
        serializer = OrdenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ruta = aplicar_orden(self.get_object(), serializer.validated_data["destino_ids"])
        return Response(self._leer(ruta))

    @action(detail=True, methods=["post"])
    def posiciones(self, request, pk=None):
        serializer = PosicionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        posicion = registrar_posicion(
            ruta=self.get_object(),
            usuario=request.user,
            latitud=serializer.validated_data["latitud"],
            longitud=serializer.validated_data["longitud"],
            precision_metros=serializer.validated_data.get("precision_metros"),
            velocidad_kmh=serializer.validated_data.get("velocidad_kmh"),
            rumbo=serializer.validated_data.get("rumbo"),
        )
        return Response(PosicionSerializer(posicion).data, status=201)

    @action(detail=True, methods=["get"])
    def seguimiento(self, request, pk=None):
        ruta = self.get_object()
        return Response(armar_seguimiento(ruta, request.user))

    @action(detail=False, methods=["get"])
    def plantilla(self, request):
        return plantilla_rutas()

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def importar(self, request):
        archivo = request.FILES.get("archivo")
        if archivo is None:
            raise ValidationError({"archivo": ["Adjunte el Excel."]})
        return Response(importar_rutas(archivo=archivo, usuario=request.user))


class NotificacionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificacionSerializer
    permission_classes = [IsAuthenticated]
    ordering_fields = ["creado_en", "id"]

    def get_queryset(self):
        return Notificacion.objects.filter(usuario=self.request.user).select_related("ruta")

    @action(detail=True, methods=["post"])
    def leer(self, request, pk=None):
        notificacion = self.get_object()
        notificacion.leida = True
        notificacion.save(update_fields=["leida"])
        return Response(NotificacionSerializer(notificacion).data)

    @action(detail=False, methods=["post"], url_path="leer-todas")
    def leer_todas(self, request):
        actualizadas = self.get_queryset().filter(leida=False).update(leida=True)
        return Response({"actualizadas": actualizadas})


class MapaRutasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rutas = puntos_de_mapa(request.user)
        return Response({"results": [armar_seguimiento(ruta, request.user) for ruta in rutas]})


def armar_seguimiento(ruta, usuario):
    activo = seguimiento_activo_para(usuario, ruta)
    es_cliente = usuario.rol_nombre == Rol.Nombre.CLIENTE
    data = {
        "ruta_id": ruta.id,
        "cliente_id": ruta.cliente_id,
        "estado": ruta.estado,
        "fecha": ruta.fecha,
        "dentro_de_lima": ruta.dentro_de_lima,
        "en_vivo": activo,
        "seguimiento_activo": activo,
        "base_origen": PuntoBreveSerializer(ruta.base_origen).data,
        "geometria": ruta.geometria_cliente if es_cliente else ruta.geometria_empresa,
        "paradas": [
            {
                "orden": parada.orden,
                "destino_id": parada.destino_id,
                "codigo_externo": parada.destino.codigo_externo,
                "estado": parada.destino.estado,
                "direccion": parada.destino.direccion,
                "distrito": parada.destino.distrito,
                "latitud": coordenada_texto(parada.destino.latitud),
                "longitud": coordenada_texto(parada.destino.longitud),
                "nombre_receptor": parada.destino.nombre_receptor,
            }
            for parada in ruta.paradas.all()
        ],
        "ultima_posicion": None,
        "recorrido": [],
    }
    if not es_cliente:
        data["base_final"] = PuntoBreveSerializer(ruta.base_final).data
    if activo and ruta.ultima_latitud is not None:
        data["ultima_posicion"] = {
            "latitud": coordenada_texto(ruta.ultima_latitud),
            "longitud": coordenada_texto(ruta.ultima_longitud),
            "registrado_en": ruta.ultima_posicion_en,
        }
        recorrido = list(ruta.posiciones.order_by("-registrado_en")[:500])
        recorrido.reverse()
        data["recorrido"] = [
            {
                "latitud": coordenada_texto(item.latitud),
                "longitud": coordenada_texto(item.longitud),
                "registrado_en": item.registrado_en,
            }
            for item in recorrido
        ]
    return data
