import django_filters
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import serializers, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from shapely.geometry import Polygon

from catalogos.lima import POLIGONO_LIMA_METROPOLITANA
from catalogos.models import Cliente, Empresa, Geocerca, Motivo, PlantillaImportacion, Punto, Vehiculo
from catalogos.services import ruc_valido, sincronizar_punto_cliente, sincronizar_punto_empresa
from config.coordenadas import CoordenadaField, validar_coordenadas
from usuarios.models import Rol
from usuarios.permissions import EsAdministrador

CAMPOS_MAPEABLES = {
    "codigo_externo",
    "fecha",
    "tipo_servicio",
    "motivo_servicio",
    "documento_receptor",
    "nombre_receptor",
    "apellido_receptor",
    "telefono_receptor",
    "direccion",
    "distrito",
    "referencia",
    "latitud",
    "longitud",
    "observaciones",
    "codigo_sede",
    "codigo_ruta",
    "ruc",
    "placa",
    "documento_conductor",
    "documentos_auxiliares",
    "codigo_base_origen",
    "codigo_base_final",
    "orden",
}


class EmpresaSerializer(serializers.ModelSerializer):
    latitud = CoordenadaField()
    longitud = CoordenadaField()

    class Meta:
        model = Empresa
        fields = [
            "id",
            "ruc",
            "razon_social",
            "telefono",
            "email",
            "direccion_principal",
            "distrito",
            "latitud",
            "longitud",
        ]

    def validate(self, attrs):
        ruc = attrs.get("ruc", getattr(self.instance, "ruc", ""))
        if not ruc_valido(str(ruc)):
            raise serializers.ValidationError({"ruc": ["El RUC debe tener 11 dígitos."]})
        latitud = attrs.get("latitud", getattr(self.instance, "latitud", None))
        longitud = attrs.get("longitud", getattr(self.instance, "longitud", None))
        if "latitud" in attrs or "longitud" in attrs or self.instance is None:
            validar_coordenadas(latitud, longitud)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        empresa = Empresa.objects.create(**validated_data)
        sincronizar_punto_empresa(empresa)
        return empresa

    @transaction.atomic
    def update(self, instance, validated_data):
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        sincronizar_punto_empresa(instance)
        return instance


class ClienteSerializer(serializers.ModelSerializer):
    latitud = CoordenadaField()
    longitud = CoordenadaField()

    class Meta:
        model = Cliente
        fields = [
            "id",
            "ruc",
            "razon_social",
            "nombre_comercial",
            "telefono",
            "email",
            "direccion_principal",
            "distrito",
            "latitud",
            "longitud",
            "activo",
        ]

    def validate(self, attrs):
        ruc = attrs.get("ruc", getattr(self.instance, "ruc", ""))
        if not ruc_valido(str(ruc)):
            raise serializers.ValidationError({"ruc": ["El RUC debe tener 11 dígitos."]})
        latitud = attrs.get("latitud", getattr(self.instance, "latitud", None))
        longitud = attrs.get("longitud", getattr(self.instance, "longitud", None))
        if "latitud" in attrs or "longitud" in attrs or self.instance is None:
            validar_coordenadas(latitud, longitud)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        cliente = Cliente.objects.create(**validated_data)
        sincronizar_punto_cliente(cliente)
        return cliente

    @transaction.atomic
    def update(self, instance, validated_data):
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        sincronizar_punto_cliente(instance)
        return instance


class PuntoSerializer(serializers.ModelSerializer):
    latitud = CoordenadaField()
    longitud = CoordenadaField()
    cliente_id = serializers.PrimaryKeyRelatedField(
        source="cliente",
        queryset=Cliente.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Punto
        fields = [
            "id",
            "cliente_id",
            "codigo",
            "nombre",
            "direccion",
            "distrito",
            "latitud",
            "longitud",
            "es_principal",
            "es_base_origen",
            "es_sede",
            "es_base_final",
            "activo",
        ]
        read_only_fields = ["es_principal"]

    def validate(self, attrs):
        if self.instance and self.instance.es_principal:
            raise serializers.ValidationError(
                {"detail": "La dirección principal se actualiza desde el cliente o desde la empresa."}
            )
        latitud = attrs.get("latitud", getattr(self.instance, "latitud", None))
        longitud = attrs.get("longitud", getattr(self.instance, "longitud", None))
        validar_coordenadas(latitud, longitud)
        cliente = attrs.get("cliente", getattr(self.instance, "cliente", None))
        es_base_final = attrs.get("es_base_final", getattr(self.instance, "es_base_final", False))
        es_base_origen = attrs.get("es_base_origen", getattr(self.instance, "es_base_origen", False))
        es_sede = attrs.get("es_sede", getattr(self.instance, "es_sede", False))
        if es_base_final and cliente is not None:
            raise serializers.ValidationError({"es_base_final": ["La base final pertenece a la empresa, sin cliente."]})
        if cliente is None and (es_base_origen or es_sede):
            raise serializers.ValidationError({"cliente_id": ["Una base de origen o una sede pertenecen a un cliente."]})
        if cliente is not None and es_base_final:
            raise serializers.ValidationError({"es_base_final": ["Un punto del cliente no puede ser la base final."]})
        if not any([es_base_origen, es_sede, es_base_final]):
            raise serializers.ValidationError({"detail": "Indique si el punto es base de origen, sede o base final."})
        codigo = attrs.get("codigo", getattr(self.instance, "codigo", ""))
        if (es_sede or es_base_origen or es_base_final) and not str(codigo or "").strip():
            raise serializers.ValidationError({"codigo": ["El código es obligatorio."]})
        return attrs


class VehiculoSerializer(serializers.ModelSerializer):
    capacidad_kg = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = Vehiculo
        fields = ["id", "placa", "marca", "modelo", "tipo", "capacidad_kg", "activo"]

    def validate_placa(self, value):
        placa = value.upper().replace(" ", "").replace("-", "")
        if len(placa) < 5:
            raise serializers.ValidationError("La placa es demasiado corta.")
        return placa


class MotivoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Motivo
        fields = ["id", "codigo", "descripcion", "aplica_a", "activo"]


class PlantillaSerializer(serializers.ModelSerializer):
    cliente_id = serializers.PrimaryKeyRelatedField(source="cliente", queryset=Cliente.objects.all())

    class Meta:
        model = PlantillaImportacion
        fields = ["id", "cliente_id", "tipo", "nombre", "mapeo_columnas", "activa"]

    def validate_mapeo_columnas(self, value):
        if not isinstance(value, dict) or not value:
            raise serializers.ValidationError("El mapeo debe ser un objeto de columnas.")
        for destino in value.values():
            if destino not in CAMPOS_MAPEABLES:
                raise serializers.ValidationError(f"Campo no reconocido: {destino}.")
        return value


class GeocercaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Geocerca
        fields = ["id", "nombre", "poligono", "activa"]
        read_only_fields = ["activa"]

    def validate_poligono(self, value):
        if not isinstance(value, list) or len(value) < 4:
            raise serializers.ValidationError("El polígono necesita al menos 4 puntos [longitud, latitud].")
        limpio = []
        for punto in value:
            if not isinstance(punto, (list, tuple)) or len(punto) != 2:
                raise serializers.ValidationError("Cada punto del polígono es [longitud, latitud].")
            try:
                validar_coordenadas(punto[1], punto[0])
            except serializers.ValidationError as exc:
                raise serializers.ValidationError("Hay un punto fuera de rango.") from exc
            limpio.append([float(punto[0]), float(punto[1])])
        if limpio[0] != limpio[-1]:
            limpio.append(limpio[0])
        poligono = Polygon([(punto[0], punto[1]) for punto in limpio])
        if not poligono.is_valid:
            raise serializers.ValidationError("El polígono no es válido.")
        return limpio


class PuntoFilter(django_filters.FilterSet):
    de_varpal = django_filters.BooleanFilter(method="filtrar_varpal")

    class Meta:
        model = Punto
        fields = ["cliente", "es_sede", "es_base_origen", "es_base_final", "es_principal", "activo"]

    def filtrar_varpal(self, queryset, name, value):
        if value:
            return queryset.filter(cliente__isnull=True)
        return queryset.filter(cliente__isnull=False)


class ClienteViewSet(viewsets.ModelViewSet):
    serializer_class = ClienteSerializer
    filterset_fields = ["activo", "ruc"]
    search_fields = ["ruc", "razon_social", "nombre_comercial"]
    ordering_fields = ["razon_social", "id"]

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [IsAuthenticated()]
        return [IsAuthenticated(), EsAdministrador()]

    def get_queryset(self):
        qs = Cliente.objects.all()
        usuario = self.request.user
        if usuario.rol_nombre == Rol.Nombre.CLIENTE:
            return qs.filter(pk=usuario.cliente_id)
        if usuario.rol_nombre != Rol.Nombre.ADMINISTRADOR:
            return qs.none()
        return qs

    def destroy(self, request, *args, **kwargs):
        cliente = self.get_object()
        cliente.activo = False
        cliente.save(update_fields=["activo"])
        sincronizar_punto_cliente(cliente)
        return Response(status=204)


class PuntoViewSet(viewsets.ModelViewSet):
    serializer_class = PuntoSerializer
    filterset_class = PuntoFilter
    search_fields = ["nombre", "codigo", "direccion", "distrito"]
    ordering_fields = ["nombre", "id"]

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [IsAuthenticated()]
        return [IsAuthenticated(), EsAdministrador()]

    def get_queryset(self):
        qs = Punto.objects.select_related("cliente")
        usuario = self.request.user
        if usuario.rol_nombre == Rol.Nombre.ADMINISTRADOR:
            return qs
        if usuario.rol_nombre == Rol.Nombre.CLIENTE:
            return qs.filter(cliente_id=usuario.cliente_id)
        if usuario.rol_nombre in {Rol.Nombre.CONDUCTOR, Rol.Nombre.AUXILIAR}:
            return qs.filter(activo=True)
        return qs.none()

    def destroy(self, request, *args, **kwargs):
        punto = self.get_object()
        if punto.es_principal:
            raise ValidationError({"detail": "La dirección principal no se elimina desde puntos."})
        try:
            punto.delete()
        except ProtectedError as exc:
            raise ValidationError({"detail": "El punto está en uso y no se puede eliminar."}) from exc
        return Response(status=204)


class VehiculoViewSet(viewsets.ModelViewSet):
    serializer_class = VehiculoSerializer
    queryset = Vehiculo.objects.all()
    filterset_fields = ["activo"]
    search_fields = ["placa", "marca", "modelo"]
    ordering_fields = ["placa", "id"]

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [IsAuthenticated()]
        return [IsAuthenticated(), EsAdministrador()]

    def get_queryset(self):
        if self.request.user.rol_nombre == Rol.Nombre.CLIENTE:
            return Vehiculo.objects.none()
        return Vehiculo.objects.all()

    def destroy(self, request, *args, **kwargs):
        vehiculo = self.get_object()
        vehiculo.activo = False
        vehiculo.save(update_fields=["activo"])
        return Response(status=204)


class MotivoViewSet(viewsets.ModelViewSet):
    serializer_class = MotivoSerializer
    filterset_fields = ["activo", "aplica_a"]
    search_fields = ["codigo", "descripcion"]
    ordering_fields = ["codigo", "id"]

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [IsAuthenticated()]
        return [IsAuthenticated(), EsAdministrador()]

    def get_queryset(self):
        usuario = self.request.user
        if usuario.rol_nombre == Rol.Nombre.CLIENTE:
            return Motivo.objects.none()
        qs = Motivo.objects.all()
        if usuario.rol_nombre != Rol.Nombre.ADMINISTRADOR:
            qs = qs.filter(activo=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        motivo = self.get_object()
        motivo.activo = False
        motivo.save(update_fields=["activo"])
        return Response(status=204)


class PlantillaImportacionViewSet(viewsets.ModelViewSet):
    serializer_class = PlantillaSerializer
    permission_classes = [IsAuthenticated, EsAdministrador]
    queryset = PlantillaImportacion.objects.select_related("cliente")
    filterset_fields = ["cliente", "tipo", "activa"]

    def destroy(self, request, *args, **kwargs):
        plantilla = self.get_object()
        plantilla.activa = False
        plantilla.save(update_fields=["activa"])
        return Response(status=204)


class EmpresaView(APIView):
    permission_classes = [IsAuthenticated, EsAdministrador]

    def get(self, request):
        empresa = Empresa.objects.first()
        if empresa is None:
            return Response(
                {"detail": "La empresa aún no tiene dirección principal.", "errores": {}},
                status=404,
            )
        return Response(EmpresaSerializer(empresa).data)

    def patch(self, request):
        empresa = Empresa.objects.first()
        if empresa is None:
            serializer = EmpresaSerializer(data=request.data)
            estado = 201
        else:
            serializer = EmpresaSerializer(empresa, data=request.data, partial=True)
            estado = 200
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=estado)


class GeocercaView(APIView):
    permission_classes = [IsAuthenticated, EsAdministrador]

    def get(self, request):
        geocerca = Geocerca.objects.filter(activa=True).order_by("-id").first()
        if geocerca is None:
            return Response({"detail": "No hay una geocerca activa.", "errores": {}}, status=404)
        return Response(GeocercaSerializer(geocerca).data)

    def put(self, request):
        geocerca = Geocerca.objects.filter(activa=True).order_by("-id").first() or Geocerca(activa=True)
        serializer = GeocercaSerializer(geocerca, data=request.data)
        serializer.is_valid(raise_exception=True)
        geocerca = serializer.save(activa=True)
        Geocerca.objects.exclude(pk=geocerca.pk).update(activa=False)
        return Response(GeocercaSerializer(geocerca).data)


def poligono_inicial():
    return POLIGONO_LIMA_METROPOLITANA
