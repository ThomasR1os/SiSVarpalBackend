import uuid

from django.conf import settings
from django.db import models


def ruta_evidencia(instance, filename):
    # Las migraciones antiguas siguen apuntando a esta función.
    return f"evidencias/{instance.destino_id}/{uuid.uuid4().hex}_{filename}"


class Destino(models.Model):
    class TipoServicio(models.TextChoices):
        ENTREGA = "ENTREGA", "Entrega"
        INTERCAMBIO = "INTERCAMBIO", "Intercambio"
        RECOJO = "RECOJO", "Recojo"
        TRASLADO = "TRASLADO", "Traslado"

    class Estado(models.TextChoices):
        NO_INICIADO = "NO_INICIADO", "No iniciado"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        EXITOSO = "EXITOSO", "Exitoso"
        FALLIDO = "FALLIDO", "Fallido"

    cliente = models.ForeignKey("catalogos.Cliente", on_delete=models.PROTECT, related_name="destinos")
    fecha = models.DateField()
    codigo_externo = models.CharField(max_length=60)
    tipo_servicio = models.CharField(max_length=20, choices=TipoServicio.choices)
    sede = models.ForeignKey(
        "catalogos.Punto",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="destinos_sede",
    )
    documento_receptor = models.CharField(max_length=20, blank=True)
    nombre_receptor = models.CharField(max_length=150, blank=True)
    apellido_receptor = models.CharField(max_length=150, blank=True)
    telefono_receptor = models.CharField(max_length=30, blank=True)
    direccion = models.CharField(max_length=300)
    distrito = models.CharField(max_length=120)
    referencia = models.CharField(max_length=300, blank=True)
    latitud = models.DecimalField(max_digits=18, decimal_places=15)
    longitud = models.DecimalField(max_digits=18, decimal_places=15)
    motivo_servicio = models.TextField()
    observaciones = models.TextField(blank=True)
    datos_extra = models.JSONField(default=dict, blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.NO_INICIADO)
    motivo = models.ForeignKey(
        "catalogos.Motivo",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="destinos",
    )
    observacion_cierre = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="destinos_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "destinos"
        verbose_name = "destino"
        ordering = ["fecha", "id"]
        indexes = [
            models.Index(fields=["cliente", "fecha", "estado"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "codigo_externo"],
                name="uniq_destino_codigo_cliente",
            ),
            models.CheckConstraint(
                condition=~models.Q(estado="FALLIDO") | models.Q(motivo__isnull=False),
                name="destino_fallido_tiene_motivo",
            ),
        ]

    def __str__(self):
        return f"{self.codigo_externo} {self.direccion}"


class Ruta(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        NO_INICIADA = "NO_INICIADA", "No iniciada"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        FINALIZADA = "FINALIZADA", "Finalizada"
        CANCELADA = "CANCELADA", "Cancelada"

    cliente = models.ForeignKey("catalogos.Cliente", on_delete=models.PROTECT, related_name="rutas")
    fecha = models.DateField()
    conductor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="rutas_conductor",
    )
    vehiculo = models.ForeignKey("catalogos.Vehiculo", on_delete=models.PROTECT, related_name="rutas")
    base_origen = models.ForeignKey(
        "catalogos.Punto",
        on_delete=models.PROTECT,
        related_name="rutas_origen",
    )
    base_final = models.ForeignKey(
        "catalogos.Punto",
        on_delete=models.PROTECT,
        related_name="rutas_final",
    )
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.BORRADOR)
    iniciada_en = models.DateTimeField(null=True, blank=True)
    llegada_base_en = models.DateTimeField(null=True, blank=True)
    finalizada_en = models.DateTimeField(null=True, blank=True)
    distancia_metros = models.PositiveIntegerField(default=0)
    duracion_segundos = models.PositiveIntegerField(default=0)
    distancia_cliente_metros = models.PositiveIntegerField(default=0)
    duracion_cliente_segundos = models.PositiveIntegerField(default=0)
    geometria_empresa = models.JSONField(default=dict, blank=True)
    geometria_cliente = models.JSONField(default=dict, blank=True)
    dentro_de_lima = models.BooleanField(default=False)
    ultima_latitud = models.DecimalField(max_digits=18, decimal_places=15, null=True, blank=True)
    ultima_longitud = models.DecimalField(max_digits=18, decimal_places=15, null=True, blank=True)
    ultima_posicion_en = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="rutas_creadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rutas"
        verbose_name = "ruta"
        ordering = ["-fecha", "-id"]
        indexes = [
            models.Index(fields=["cliente", "fecha"]),
            models.Index(fields=["conductor", "estado"]),
            models.Index(fields=["estado", "dentro_de_lima"]),
        ]

    def __str__(self):
        return f"Ruta {self.id} {self.fecha}"


class RutaAuxiliar(models.Model):
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name="auxiliares")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="rutas_auxiliar",
    )

    class Meta:
        db_table = "ruta_auxiliares"
        constraints = [
            models.UniqueConstraint(fields=["ruta", "usuario"], name="uniq_ruta_auxiliar"),
        ]


class RutaDestino(models.Model):
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name="paradas")
    destino = models.OneToOneField(Destino, on_delete=models.PROTECT, related_name="asignacion")
    orden = models.PositiveIntegerField()
    hora_estimada = models.DateTimeField(null=True, blank=True)
    hora_llegada = models.DateTimeField(null=True, blank=True)
    hora_salida = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ruta_destinos"
        ordering = ["orden"]
        constraints = [
            models.UniqueConstraint(fields=["ruta", "orden"], name="uniq_ruta_orden"),
        ]


class Evidencia(models.Model):
    destino = models.ForeignKey(Destino, on_delete=models.CASCADE, related_name="evidencias")
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="evidencias",
    )
    archivo = models.URLField(max_length=1000)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "evidencias"
        ordering = ["creado_en"]


class Posicion(models.Model):
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name="posiciones")
    latitud = models.DecimalField(max_digits=18, decimal_places=15)
    longitud = models.DecimalField(max_digits=18, decimal_places=15)
    precision_metros = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    velocidad_kmh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rumbo = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "posiciones"
        ordering = ["registrado_en"]
        indexes = [
            models.Index(fields=["ruta", "registrado_en"]),
        ]


class Notificacion(models.Model):
    class Tipo(models.TextChoices):
        RUTA_INICIADA = "RUTA_INICIADA", "Ruta iniciada"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notificaciones",
    )
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name="notificaciones")
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    titulo = models.CharField(max_length=150)
    cuerpo = models.TextField()
    leida = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificaciones"
        ordering = ["-creado_en"]
