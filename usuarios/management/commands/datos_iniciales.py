import os

from django.core.management.base import BaseCommand

from catalogos.lima import POLIGONO_LIMA_METROPOLITANA
from catalogos.models import Geocerca, Motivo
from usuarios.models import Rol, Usuario


MOTIVOS = [
    ("AUSENTE", "No había nadie en el destino", Motivo.AplicaA.AMBOS),
    ("DIRECCION", "Dirección incorrecta o no ubicada", Motivo.AplicaA.NO_LLEGO),
    ("CERRADO", "Local cerrado", Motivo.AplicaA.NO_LLEGO),
    ("RECHAZO", "El receptor rechazó el servicio", Motivo.AplicaA.SERVICIO_FALLIDO),
    ("DANADA", "Mercadería dañada o incompleta", Motivo.AplicaA.SERVICIO_FALLIDO),
]


class Command(BaseCommand):
    help = "Crea roles, la geocerca de Lima, motivos de incumplimiento y el administrador inicial."

    def handle(self, *args, **options):
        for nombre, descripcion in Rol.Nombre.choices:
            Rol.objects.get_or_create(nombre=nombre, defaults={"descripcion": descripcion})
        Geocerca.objects.get_or_create(
            nombre="Lima metropolitana",
            defaults={"poligono": POLIGONO_LIMA_METROPOLITANA, "activa": True},
        )
        for codigo, descripcion, aplica_a in MOTIVOS:
            Motivo.objects.get_or_create(
                codigo=codigo,
                defaults={"descripcion": descripcion, "aplica_a": aplica_a, "activo": True},
            )
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not password:
            self.stdout.write(self.style.WARNING("ADMIN_PASSWORD no está definido. No se creó el administrador."))
            return
        if Usuario.objects.filter(username="admin").exists():
            self.stdout.write("El administrador ya existe.")
            return
        Usuario.objects.create_user(
            username="admin",
            password=password,
            email="admin@varpal.local",
            nombre="Administrador",
            apellido="Varpal",
            documento="00000000",
            rol=Rol.objects.get(nombre=Rol.Nombre.ADMINISTRADOR),
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(self.style.SUCCESS("Datos iniciales listos. Correo: admin@varpal.local"))
