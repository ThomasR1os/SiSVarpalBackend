from django.db import models


class Empresa(models.Model):
    ruc = models.CharField(max_length=11, unique=True)
    razon_social = models.CharField(max_length=200)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    direccion_principal = models.CharField(max_length=300)
    distrito = models.CharField(max_length=120)
    latitud = models.DecimalField(max_digits=18, decimal_places=15)
    longitud = models.DecimalField(max_digits=18, decimal_places=15)

    class Meta:
        db_table = "empresa"
        verbose_name = "empresa"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.razon_social


class Cliente(models.Model):
    ruc = models.CharField(max_length=11, unique=True)
    razon_social = models.CharField(max_length=200)
    nombre_comercial = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    direccion_principal = models.CharField(max_length=300)
    distrito = models.CharField(max_length=120)
    latitud = models.DecimalField(max_digits=18, decimal_places=15)
    longitud = models.DecimalField(max_digits=18, decimal_places=15)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "clientes"
        verbose_name = "cliente"
        ordering = ["razon_social"]

    def __str__(self):
        return f"{self.ruc} {self.razon_social}"


class Punto(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="puntos",
    )
    codigo = models.CharField(max_length=40, blank=True, default="")
    nombre = models.CharField(max_length=200)
    direccion = models.CharField(max_length=300)
    distrito = models.CharField(max_length=120)
    latitud = models.DecimalField(max_digits=18, decimal_places=15)
    longitud = models.DecimalField(max_digits=18, decimal_places=15)
    es_principal = models.BooleanField(default=False)
    es_base_origen = models.BooleanField(default=False)
    es_sede = models.BooleanField(default=False)
    es_base_final = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "puntos"
        verbose_name = "punto"
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "codigo"],
                condition=models.Q(cliente__isnull=False) & ~models.Q(codigo=""),
                name="uniq_punto_codigo_por_cliente",
            ),
            models.UniqueConstraint(
                fields=["codigo"],
                condition=models.Q(cliente__isnull=True) & ~models.Q(codigo=""),
                name="uniq_punto_codigo_varpal",
            ),
            models.UniqueConstraint(
                fields=["cliente"],
                condition=models.Q(es_principal=True, cliente__isnull=False),
                name="uniq_punto_principal_cliente",
            ),
            models.UniqueConstraint(
                fields=["es_principal"],
                condition=models.Q(es_principal=True, cliente__isnull=True),
                name="uniq_punto_principal_varpal",
            ),
        ]

    def __str__(self):
        return self.nombre


class Vehiculo(models.Model):
    placa = models.CharField(max_length=10, unique=True)
    marca = models.CharField(max_length=80, blank=True)
    modelo = models.CharField(max_length=80, blank=True)
    tipo = models.CharField(max_length=80, blank=True)
    capacidad_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "vehiculos"
        verbose_name = "vehículo"
        ordering = ["placa"]

    def save(self, *args, **kwargs):
        self.placa = self.placa.upper().replace(" ", "").replace("-", "")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.placa


class Motivo(models.Model):
    class AplicaA(models.TextChoices):
        NO_LLEGO = "NO_LLEGO", "No llegó"
        SERVICIO_FALLIDO = "SERVICIO_FALLIDO", "Servicio fallido"
        AMBOS = "AMBOS", "Ambos"

    codigo = models.CharField(max_length=40, unique=True)
    descripcion = models.CharField(max_length=300)
    aplica_a = models.CharField(max_length=20, choices=AplicaA.choices, default=AplicaA.AMBOS)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "motivos"
        verbose_name = "motivo"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} {self.descripcion}"


class Geocerca(models.Model):
    nombre = models.CharField(max_length=120)
    poligono = models.JSONField()
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "geocercas"
        verbose_name = "geocerca"

    def __str__(self):
        return self.nombre


class PlantillaImportacion(models.Model):
    class Tipo(models.TextChoices):
        DESTINOS = "DESTINOS", "Destinos"
        RUTAS = "RUTAS", "Rutas"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="plantillas")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    nombre = models.CharField(max_length=150)
    mapeo_columnas = models.JSONField(default=dict)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "plantillas_importacion"
        verbose_name = "plantilla de importación"
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "tipo"],
                condition=models.Q(activa=True),
                name="uniq_plantilla_activa",
            )
        ]

    def __str__(self):
        return f"{self.cliente_id} {self.tipo} {self.nombre}"
