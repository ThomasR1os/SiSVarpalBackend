from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from usuarios.models import Rol, Usuario

CLAVE = "ClaveSegura123"


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    AUTH_PASSWORD_VALIDATORS=[],
)
class SesionUnicaTests(TestCase):
    def setUp(self):
        rol = Rol.objects.create(nombre=Rol.Nombre.ADMINISTRADOR)
        Usuario.objects.create(
            username="admin",
            email="admin@varpal.local",
            password=make_password(CLAVE),
            nombre="Admin",
            apellido="Varpal",
            documento="00000000",
            rol=rol,
        )
        self.client = APIClient()

    def test_un_ingreso_nuevo_cierra_el_anterior(self):
        primero = self.client.post("/api/auth/login/", {"email": "admin@varpal.local", "password": CLAVE}, format="json")
        self.assertEqual(primero.status_code, 200, primero.content)
        segundo = self.client.post("/api/auth/login/", {"email": "admin@varpal.local", "password": CLAVE}, format="json")
        self.assertEqual(segundo.status_code, 200, segundo.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {primero.data['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        refresco = self.client.post("/api/auth/refresh/", {"refresh": primero.data["refresh"]}, format="json")
        self.assertEqual(refresco.status_code, 401, refresco.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {segundo.data['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
