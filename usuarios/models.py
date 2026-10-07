from django.contrib.auth.models import AbstractUser
from django.db import models


class Rol(models.Model):
    class Nombre(models.TextChoices):
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
        CONDUCTOR = "CONDUCTOR", "Conductor"
        AUXILIAR = "AUXILIAR", "Auxiliar"
        CLIENTE = "CLIENTE", "Cliente"

    nombre = models.CharField(max_length=20, unique=True, choices=Nombre.choices)
    descripcion = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "roles"
        verbose_name = "rol"

    def __str__(self):
        return self.nombre


class Usuario(AbstractUser):
    email = models.EmailField(unique=True)
    nombre = models.CharField(max_length=150)
    apellido = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    documento = models.CharField(max_length=20, unique=True)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="usuarios")
    cliente = models.ForeignKey(
        "catalogos.Cliente",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="usuarios",
    )

    class Meta:
        db_table = "usuarios"
        verbose_name = "usuario"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} {self.apellido}".strip() or self.email

    @property
    def rol_nombre(self):
        if self.rol_id is None:
            return ""
        return self.rol.nombre


class SesionActiva(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="sesion_activa")
    refresh_jti = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    expira_en = models.DateTimeField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sesiones_activas"
        verbose_name = "sesión activa"
