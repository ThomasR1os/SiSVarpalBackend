from django.conf import settings
from rest_framework import serializers

from catalogos.models import Cliente, Motivo, Punto, Vehiculo
from catalogos.serializers import PuntoBreveSerializer, VehiculoBreveSerializer
from operaciones.models import Destino, Evidencia, Notificacion, Posicion, Ruta
from operaciones.services.destinos import actualizar_destino, crear_destino
from operaciones.services.geo import distancia_de_linea, segundos_de_viaje
from operaciones.services.rutas import actualizar_ruta, crear_ruta
from config.coordenadas import CoordenadaField, coordenada_texto
from usuarios.models import Rol, Usuario
from usuarios.serializers import UsuarioBreveSerializer


class DestinoSerializer(serializers.ModelSerializer):
    latitud = CoordenadaField()
    longitud = CoordenadaField()
    cliente_id = serializers.IntegerField(source="cliente.id", read_only=True)
    sede_id = serializers.IntegerField(source="sede.id", read_only=True, allow_null=True)
    motivo_id = serializers.IntegerField(source="motivo.id", read_only=True, allow_null=True)
    ruta_id = serializers.SerializerMethodField()

    class Meta:
        model = Destino
        fields = [
            "id",
            "cliente_id",
            "fecha",
            "codigo_externo",
            "tipo_servicio",
            "sede_id",
            "documento_receptor",
            "nombre_receptor",
            "apellido_receptor",
            "telefono_receptor",
            "direccion",
            "distrito",
            "referencia",
            "latitud",
            "longitud",
            "motivo_servicio",
            "observaciones",
            "datos_extra",
            "estado",
            "motivo_id",
            "observacion_cierre",
            "ruta_id",
            "creado_en",
            "actualizado_en",
        ]

    def get_ruta_id(self, obj):
        if hasattr(obj, "asignacion"):
            return obj.asignacion.ruta_id
        return None


class DestinoWriteSerializer(serializers.Serializer):
    cliente_id = serializers.PrimaryKeyRelatedField(source="cliente", queryset=Cliente.objects.all())
    fecha = serializers.DateField()
    codigo_externo = serializers.CharField()
    tipo_servicio = serializers.ChoiceField(choices=Destino.TipoServicio.choices)
    sede_id = serializers.PrimaryKeyRelatedField(
        source="sede", queryset=Punto.objects.all(), required=False, allow_null=True
    )
    documento_receptor = serializers.CharField(required=False, allow_blank=True)
    nombre_receptor = serializers.CharField(required=False, allow_blank=True)
    apellido_receptor = serializers.CharField(required=False, allow_blank=True)
    telefono_receptor = serializers.CharField(required=False, allow_blank=True)
    direccion = serializers.CharField(required=False, allow_blank=True)
    distrito = serializers.CharField(required=False, allow_blank=True)
    referencia = serializers.CharField(required=False, allow_blank=True)
    latitud = CoordenadaField(required=False, allow_null=True)
    longitud = CoordenadaField(required=False, allow_null=True)
    motivo_servicio = serializers.CharField()
    observaciones = serializers.CharField(required=False, allow_blank=True)
    datos_extra = serializers.JSONField(required=False)

    def create(self, validated_data):
        cliente = validated_data.pop("cliente")
        return crear_destino(cliente=cliente, datos=validated_data, usuario=self.context["request"].user)

    def update(self, instance, validated_data):
        validated_data.pop("cliente", None)
        return actualizar_destino(instance, validated_data)


class ParadaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    orden = serializers.IntegerField()
    destino_id = serializers.IntegerField()
    codigo_externo = serializers.CharField(source="destino.codigo_externo")
    tipo_servicio = serializers.CharField(source="destino.tipo_servicio")
    estado = serializers.CharField(source="destino.estado")
    direccion = serializers.CharField(source="destino.direccion")
    distrito = serializers.CharField(source="destino.distrito")
    latitud = CoordenadaField(source="destino.latitud")
    longitud = CoordenadaField(source="destino.longitud")
    nombre_receptor = serializers.CharField(source="destino.nombre_receptor")
    apellido_receptor = serializers.CharField(source="destino.apellido_receptor")
    hora_estimada = serializers.DateTimeField(allow_null=True)
    hora_llegada = serializers.DateTimeField(allow_null=True)
    hora_salida = serializers.DateTimeField(allow_null=True)


class RutaSerializer(serializers.ModelSerializer):
    cliente_id = serializers.IntegerField(source="cliente.id")
    cliente_nombre = serializers.CharField(source="cliente.razon_social")
    conductor = UsuarioBreveSerializer()
    vehiculo = VehiculoBreveSerializer()
    auxiliares = serializers.SerializerMethodField()
    base_origen = PuntoBreveSerializer()
    base_final = PuntoBreveSerializer()
    paradas = ParadaSerializer(many=True)

    class Meta:
        model = Ruta
        fields = [
            "id",
            "cliente_id",
            "cliente_nombre",
            "fecha",
            "estado",
            "conductor",
            "vehiculo",
            "auxiliares",
            "base_origen",
            "base_final",
            "paradas",
            "distancia_metros",
            "duracion_segundos",
            "geometria_cliente",
            "geometria_empresa",
            "dentro_de_lima",
            "iniciada_en",
            "llegada_base_en",
            "finalizada_en",
            "ultima_latitud",
            "ultima_longitud",
            "ultima_posicion_en",
        ]

    def get_auxiliares(self, obj):
        return UsuarioBreveSerializer([item.usuario for item in obj.auxiliares.all()], many=True).data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        usuario = getattr(request, "user", None)
        if usuario is not None and getattr(usuario, "rol_nombre", "") == Rol.Nombre.CLIENTE:
            data.pop("base_final", None)
            data.pop("geometria_empresa", None)
            if instance.distancia_cliente_metros or instance.duracion_cliente_segundos:
                data["distancia_metros"] = instance.distancia_cliente_metros
                data["duracion_segundos"] = instance.duracion_cliente_segundos
            else:
                metros = distancia_de_linea(instance.geometria_cliente)
                data["distancia_metros"] = metros
                data["duracion_segundos"] = segundos_de_viaje(metros)
            data["ultima_latitud"] = None
            data["ultima_longitud"] = None
            data["ultima_posicion_en"] = None
        else:
            data["ultima_latitud"] = coordenada_texto(instance.ultima_latitud)
            data["ultima_longitud"] = coordenada_texto(instance.ultima_longitud)
        return data


class RutaWriteSerializer(serializers.Serializer):
    cliente_id = serializers.PrimaryKeyRelatedField(source="cliente", queryset=Cliente.objects.all())
    fecha = serializers.DateField()
    conductor_id = serializers.PrimaryKeyRelatedField(
        source="conductor",
        queryset=Usuario.objects.filter(rol__nombre=Rol.Nombre.CONDUCTOR, is_active=True),
    )
    vehiculo_id = serializers.PrimaryKeyRelatedField(source="vehiculo", queryset=Vehiculo.objects.filter(activo=True))
    auxiliar_ids = serializers.PrimaryKeyRelatedField(
        source="auxiliares",
        many=True,
        required=False,
        queryset=Usuario.objects.filter(rol__nombre=Rol.Nombre.AUXILIAR, is_active=True),
        default=list,
    )
    base_origen_id = serializers.PrimaryKeyRelatedField(
        source="base_origen",
        queryset=Punto.objects.filter(es_base_origen=True, activo=True),
        required=False,
        allow_null=True,
        default=None,
    )
    base_final_id = serializers.PrimaryKeyRelatedField(
        source="base_final",
        queryset=Punto.objects.filter(es_base_final=True, activo=True),
        required=False,
        allow_null=True,
        default=None,
    )
    destino_ids = serializers.PrimaryKeyRelatedField(
        source="destinos",
        many=True,
        required=False,
        queryset=Destino.objects.all(),
    )
    optimizar = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if self.instance is None and not attrs.get("destinos"):
            raise serializers.ValidationError({"destino_ids": ["La ruta necesita al menos un destino."]})
        return attrs

    def create(self, validated_data):
        return crear_ruta(
            cliente=validated_data["cliente"],
            fecha=validated_data["fecha"],
            conductor=validated_data["conductor"],
            vehiculo=validated_data["vehiculo"],
            auxiliares=validated_data.get("auxiliares", []),
            base_origen=validated_data.get("base_origen"),
            base_final=validated_data.get("base_final"),
            destinos=validated_data["destinos"],
            creado_por=self.context["request"].user,
            optimizar=validated_data.get("optimizar", False),
        )

    def update(self, instance, validated_data):
        validated_data.pop("cliente", None)
        return actualizar_ruta(instance, validated_data)


class OptimizarSerializer(serializers.Serializer):
    cliente_id = serializers.PrimaryKeyRelatedField(source="cliente", queryset=Cliente.objects.all())
    fecha = serializers.DateField()
    base_origen_id = serializers.PrimaryKeyRelatedField(
        source="base_origen",
        queryset=Punto.objects.filter(es_base_origen=True, activo=True),
        required=False,
        allow_null=True,
    )
    base_final_id = serializers.PrimaryKeyRelatedField(
        source="base_final",
        queryset=Punto.objects.filter(es_base_final=True, activo=True),
        required=False,
        allow_null=True,
    )
    destino_ids = serializers.PrimaryKeyRelatedField(source="destinos", many=True, queryset=Destino.objects.all())


class OrdenSerializer(serializers.Serializer):
    destino_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class ReprogramarSerializer(serializers.Serializer):
    fecha = serializers.DateField()


class PosicionSerializer(serializers.ModelSerializer):
    latitud = CoordenadaField()
    longitud = CoordenadaField()
    precision_metros = serializers.FloatField(required=False, allow_null=True)
    velocidad_kmh = serializers.FloatField(required=False, allow_null=True)
    rumbo = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = Posicion
        fields = [
            "id",
            "latitud",
            "longitud",
            "precision_metros",
            "velocidad_kmh",
            "rumbo",
            "registrado_en",
        ]
        read_only_fields = ["id", "registrado_en"]


class EvidenciaSerializer(serializers.ModelSerializer):
    archivo = serializers.SerializerMethodField()

    class Meta:
        model = Evidencia
        fields = ["id", "archivo", "creado_en"]

    def get_archivo(self, obj):
        url = obj.archivo or ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        request = self.context.get("request")
        ruta = url if url.startswith("/") else f"{settings.MEDIA_URL}{url}"
        if request is None:
            return ruta
        return request.build_absolute_uri(ruta)


class NotificacionSerializer(serializers.ModelSerializer):
    ruta_id = serializers.IntegerField(source="ruta.id")

    class Meta:
        model = Notificacion
        fields = ["id", "ruta_id", "tipo", "titulo", "cuerpo", "leida", "creado_en"]


class CierreSerializer(serializers.Serializer):
    resultado = serializers.ChoiceField(choices=[Destino.Estado.EXITOSO, Destino.Estado.FALLIDO])
    motivo_id = serializers.PrimaryKeyRelatedField(
        source="motivo",
        queryset=Motivo.objects.filter(activo=True),
        required=False,
        allow_null=True,
    )
    observacion = serializers.CharField(required=False, allow_blank=True)
