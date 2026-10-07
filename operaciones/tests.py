from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from catalogos.lima import POLIGONO_LIMA_METROPOLITANA
from config.coordenadas import coordenada_texto
from catalogos.models import Cliente, Empresa, Geocerca, Motivo, Punto, Vehiculo
from catalogos.services import sincronizar_punto_cliente, sincronizar_punto_empresa
from operaciones.models import Destino, Evidencia, Ruta
from operaciones.services.calles import MotorNoDisponible
from usuarios.models import Rol, Usuario

CLAVE = "ClaveSegura123"


def foto():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
    return SimpleUploadedFile("foto.png", buffer.getvalue(), content_type="image/png")


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    AUTH_PASSWORD_VALIDATORS=[],
)
class ReglasApiTests(TestCase):
    def setUp(self):
        self._nube = patch(
            "operaciones.services.destinos.subir_foto",
            side_effect=lambda archivo, destino_id: (
                f"https://res.cloudinary.com/zwpuvmw7/image/upload/varpal/evidencias/{destino_id}/foto.png"
            ),
        )
        self._nube.start()
        self.addCleanup(self._nube.stop)
        self.client = APIClient()
        roles = {
            nombre: Rol.objects.create(nombre=nombre)
            for nombre, _etiqueta in Rol.Nombre.choices
        }
        Geocerca.objects.create(nombre="Lima metropolitana", poligono=POLIGONO_LIMA_METROPOLITANA, activa=True)
        self.empresa = Empresa.objects.create(
            ruc="20999999991",
            razon_social="Varpal",
            direccion_principal="Av. Empresa 100",
            distrito="Cercado de Lima",
            latitud=-12.046374,
            longitud=-77.042793,
        )
        sincronizar_punto_empresa(self.empresa)
        self.cliente = Cliente.objects.create(
            ruc="20111111111",
            razon_social="Cliente Demo",
            direccion_principal="Av. Cliente 200",
            distrito="Miraflores",
            latitud=-12.090000,
            longitud=-77.050000,
        )
        sincronizar_punto_cliente(self.cliente)
        self.vehiculo = Vehiculo.objects.create(placa="ABC123")
        self.motivo = Motivo.objects.create(codigo="AUSENTE", descripcion="No había nadie", aplica_a="AMBOS")
        self.admin = Usuario.objects.create(
            username="admin",
            email="admin@varpal.local",
            password=make_password(CLAVE),
            nombre="Admin",
            apellido="Varpal",
            documento="00000000",
            rol=roles["ADMINISTRADOR"],
        )
        self.conductor = Usuario.objects.create(
            username="conductor",
            email="conductor@varpal.local",
            password=make_password(CLAVE),
            nombre="Luis",
            apellido="Perez",
            documento="87654321",
            rol=roles["CONDUCTOR"],
        )
        self.usuario_cliente = Usuario.objects.create(
            username="cliente",
            email="cliente@demo.pe",
            password=make_password(CLAVE),
            nombre="Ana",
            apellido="Cliente",
            documento="11112222",
            rol=roles["CLIENTE"],
            cliente=self.cliente,
        )
        self.hoy = timezone.localdate()
        self.destino = Destino.objects.create(
            cliente=self.cliente,
            fecha=self.hoy,
            codigo_externo="G-001",
            tipo_servicio=Destino.TipoServicio.ENTREGA,
            documento_receptor="12345678",
            nombre_receptor="Ana",
            apellido_receptor="Diaz",
            telefono_receptor="999999999",
            direccion="Calle Destino 10",
            distrito="Miraflores",
            latitud=-12.100000,
            longitud=-77.040000,
            motivo_servicio="Pedido",
            creado_por=self.admin,
        )
        self.destino_lejos = Destino.objects.create(
            cliente=self.cliente,
            fecha=self.hoy,
            codigo_externo="G-002",
            tipo_servicio=Destino.TipoServicio.ENTREGA,
            documento_receptor="12345678",
            nombre_receptor="Luis",
            apellido_receptor="Rojas",
            telefono_receptor="988888888",
            direccion="Calle Lejana 99",
            distrito="San Isidro",
            latitud=-12.200000,
            longitud=-77.020000,
            motivo_servicio="Pedido",
            creado_por=self.admin,
        )

    def autenticar(self, usuario):
        self.client.force_authenticate(usuario)

    def test_importar_rechaza_fila_sin_coordenadas(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import Workbook

        libro = Workbook()
        hoja = libro.active
        hoja.append(
            [
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
            ]
        )
        hoja.append(
            ["OK-1", self.hoy.isoformat(), "ENTREGA", "Pedido", "123", "Ana", "Diaz", "999", "Av 1", "Miraflores", "", -12.11, -77.03, "", ""]
        )
        hoja.append(
            ["MAL-1", self.hoy.isoformat(), "ENTREGA", "Pedido", "123", "Ana", "Diaz", "999", "Av 2", "Miraflores", "", None, None, "", ""]
        )
        buffer = BytesIO()
        libro.save(buffer)
        buffer.seek(0)
        archivo = SimpleUploadedFile(
            "destinos.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.autenticar(self.admin)
        respuesta = self.client.post(
            "/api/destinos/importar/",
            {"cliente_id": self.cliente.id, "archivo": archivo},
            format="multipart",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data["creados"], 1)
        self.assertEqual(len(respuesta.data["rechazados"]), 1)
        self.assertIn("latitud", respuesta.data["rechazados"][0]["errores"][0])

    def _ruta_en_proceso(self):
        self.autenticar(self.admin)
        creada = self.client.post(
            "/api/rutas/",
            {
                "cliente_id": self.cliente.id,
                "fecha": self.hoy.isoformat(),
                "conductor_id": self.conductor.id,
                "vehiculo_id": self.vehiculo.id,
                "destino_ids": [self.destino.id],
            },
            format="json",
        )
        self.assertEqual(creada.status_code, 201, creada.content)
        ruta_id = creada.data["id"]
        self.assertIn("base_final", creada.data)
        confirmada = self.client.post(f"/api/rutas/{ruta_id}/confirmar/")
        self.assertEqual(confirmada.status_code, 200, confirmada.content)
        self.autenticar(self.conductor)
        iniciada = self.client.post(f"/api/rutas/{ruta_id}/iniciar/")
        self.assertEqual(iniciada.status_code, 200, iniciada.content)
        self.assertEqual(iniciada.data["estado"], Ruta.Estado.EN_PROCESO)
        return ruta_id

    def test_cierre_exige_foto_y_motivo_si_falla(self):
        ruta_id = self._ruta_en_proceso()
        self.autenticar(self.conductor)
        sin_foto = self.client.post(
            f"/api/destinos/{self.destino.id}/cerrar/",
            {"resultado": "EXITOSO"},
            format="multipart",
        )
        self.assertEqual(sin_foto.status_code, 400, sin_foto.content)
        self.assertIn("fotos", sin_foto.data["errores"])
        sin_motivo = self.client.post(
            f"/api/destinos/{self.destino.id}/cerrar/",
            {"resultado": "FALLIDO", "fotos": foto()},
            format="multipart",
        )
        self.assertEqual(sin_motivo.status_code, 400, sin_motivo.content)
        self.assertIn("motivo_id", sin_motivo.data["errores"])
        self.destino.refresh_from_db()
        self.assertEqual(self.destino.estado, Destino.Estado.EN_PROCESO)
        self.assertEqual(Ruta.objects.get(pk=ruta_id).estado, Ruta.Estado.EN_PROCESO)

    def test_seguimiento_del_cliente_oculta_la_base_final(self):
        ruta_id = self._ruta_en_proceso()
        self.autenticar(self.conductor)
        posicion = self.client.post(
            f"/api/rutas/{ruta_id}/posiciones/",
            {"latitud": -12.095, "longitud": -77.045, "precision_metros": 8},
            format="json",
        )
        self.assertEqual(posicion.status_code, 201, posicion.content)
        self.autenticar(self.usuario_cliente)
        seguimiento = self.client.get(f"/api/rutas/{ruta_id}/seguimiento/")
        self.assertEqual(seguimiento.status_code, 200, seguimiento.content)
        self.assertNotIn("base_final", seguimiento.data)
        self.assertTrue(seguimiento.data["en_vivo"])
        self.assertIsNotNone(seguimiento.data["ultima_posicion"])
        ultimo = seguimiento.data["geometria"]["coordinates"][-1]
        base_final = Punto.objects.get(cliente__isnull=True, es_principal=True)
        self.assertNotEqual(ultimo, [float(base_final.longitud), float(base_final.latitud)])
        self.autenticar(self.conductor)
        cerrado = self.client.post(
            f"/api/destinos/{self.destino.id}/cerrar/",
            {"resultado": "EXITOSO", "fotos": foto()},
            format="multipart",
        )
        self.assertEqual(cerrado.status_code, 200, cerrado.content)
        evidencia = Evidencia.objects.get(destino=self.destino)
        self.assertTrue(evidencia.archivo.startswith("https://res.cloudinary.com/"))
        self.autenticar(self.usuario_cliente)
        despues = self.client.get(f"/api/rutas/{ruta_id}/seguimiento/")
        self.assertFalse(despues.data["en_vivo"])
        self.assertIsNone(despues.data["ultima_posicion"])
        self.assertEqual(despues.data["recorrido"], [])

    def test_optimizar_ordena_por_cercania_sin_guardar(self):
        self.autenticar(self.admin)
        respuesta = self.client.post(
            "/api/rutas/optimizar/",
            {
                "cliente_id": self.cliente.id,
                "fecha": self.hoy.isoformat(),
                "destino_ids": [self.destino_lejos.id, self.destino.id],
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data["destino_ids"][0], self.destino.id)
        self.assertEqual(Ruta.objects.count(), 0)

    def test_alta_guarda_la_calle_y_el_cliente_no_ve_el_regreso(self):
        with patch("operaciones.services.calles.pedir_ruta", side_effect=_ruta_por_calles):
            creada = self._crear_ruta([self.destino.id])
        empresa = creada.data["geometria_empresa"]["coordinates"]
        cliente = creada.data["geometria_cliente"]["coordinates"]
        self.assertGreater(len(empresa), 3)
        self.assertGreater(len(cliente), 2)
        self.assertLess(len(cliente), len(empresa))
        self.assertEqual(creada.data["distancia_metros"], 3000)
        self.assertEqual(creada.data["duracion_segundos"], 300)
        self.assertNotEqual(cliente[-1], empresa[-1])
        leida = self.client.get(f"/api/rutas/{creada.data['id']}/")
        self.assertEqual(leida.data["geometria_empresa"]["coordinates"], empresa)
        self.client.post(f"/api/rutas/{creada.data['id']}/confirmar/")
        self.autenticar(self.usuario_cliente)
        vista = self.client.get(f"/api/rutas/{creada.data['id']}/")
        self.assertEqual(vista.status_code, 200, vista.content)
        self.assertNotIn("geometria_empresa", vista.data)
        self.assertNotIn("base_final", vista.data)
        self.assertEqual(vista.data["distancia_metros"], 1000)
        self.assertEqual(vista.data["duracion_segundos"], 100)
        self.assertEqual(vista.data["geometria_cliente"]["coordinates"], cliente)
        seguimiento = self.client.get(f"/api/rutas/{creada.data['id']}/seguimiento/")
        self.assertEqual(seguimiento.data["geometria"]["coordinates"], cliente)
        self.autenticar(self.admin)
        empresa_vivo = self.client.get(f"/api/rutas/{creada.data['id']}/seguimiento/")
        self.assertEqual(empresa_vivo.data["geometria"]["coordinates"], empresa)

    def test_si_el_motor_no_responde_guarda_la_recta(self):
        with patch("operaciones.services.calles.pedir_ruta", side_effect=MotorNoDisponible("caído")):
            creada = self._crear_ruta([self.destino.id])
        self.assertEqual(creada.status_code, 201, creada.content)
        self.assertEqual(len(creada.data["geometria_cliente"]["coordinates"]), 2)
        self.assertEqual(len(creada.data["geometria_empresa"]["coordinates"]), 3)

    def test_patch_de_conductor_no_cambia_la_geometria(self):
        with patch("operaciones.services.calles.pedir_ruta", side_effect=MotorNoDisponible("caído")):
            creada = self._crear_ruta([self.destino.id])
        ruta = Ruta.objects.get(pk=creada.data["id"])
        sentinel = {"type": "LineString", "coordinates": [[-77.2, -12.2], [-77.21, -12.21], [-77.22, -12.19]]}
        ruta.geometria_empresa = sentinel
        ruta.geometria_cliente = sentinel
        ruta.save(update_fields=["geometria_empresa", "geometria_cliente"])

        def prohibido(*args, **kwargs):
            raise AssertionError("no debía recalcular la geometría")

        with patch("operaciones.services.calles.pedir_ruta", side_effect=prohibido):
            respuesta = self.client.patch(
                f"/api/rutas/{ruta.id}/",
                {"conductor_id": self.conductor.id},
                format="json",
            )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data["geometria_empresa"]["coordinates"], sentinel["coordinates"])

    def test_patch_de_orden_recalcula_por_la_calle(self):
        with patch("operaciones.services.calles.pedir_ruta", side_effect=MotorNoDisponible("caído")):
            creada = self._crear_ruta([self.destino_lejos.id, self.destino.id])
        with patch("operaciones.services.calles.pedir_ruta", side_effect=_ruta_por_calles):
            respuesta = self.client.patch(
                f"/api/rutas/{creada.data['id']}/orden/",
                {"destino_ids": [self.destino.id, self.destino_lejos.id]},
                format="json",
            )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertGreater(len(respuesta.data["geometria_empresa"]["coordinates"]), 4)
        self.assertEqual(
            [parada["destino_id"] for parada in respuesta.data["paradas"]],
            [self.destino.id, self.destino_lejos.id],
        )
        self.assertEqual(respuesta.data["distancia_metros"], 6000)
        self.assertEqual(respuesta.data["duracion_segundos"], 600)

    def test_patch_de_bases_recalcula_por_la_calle(self):
        otra = Punto.objects.create(
            cliente=self.cliente,
            codigo="BASE-SUR",
            nombre="Base sur",
            direccion="Av. Sur 1",
            distrito="Surco",
            latitud=-12.15,
            longitud=-76.99,
            es_base_origen=True,
            activo=True,
        )
        with patch("operaciones.services.calles.pedir_ruta", side_effect=MotorNoDisponible("caído")):
            creada = self._crear_ruta([self.destino.id])
        with patch("operaciones.services.calles.pedir_ruta", side_effect=_ruta_por_calles) as pedido:
            respuesta = self.client.patch(
                f"/api/rutas/{creada.data['id']}/",
                {"base_origen_id": otra.id},
                format="json",
            )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertGreater(len(respuesta.data["geometria_empresa"]["coordinates"]), 3)
        self.assertEqual(pedido.call_args.args[0][0], (float(otra.latitud), float(otra.longitud)))

    def test_optimizar_usa_la_distancia_por_calle_sin_la_base_de_varpal(self):
        self.autenticar(self.admin)
        capturados = []

        def matriz(puntos):
            capturados.append(puntos)
            tabla = [[None for _ in puntos] for _ in puntos]
            tabla[0][1] = 9000
            tabla[0][2] = 100
            tabla[1][2] = 400
            tabla[2][1] = 400
            return tabla

        with (
            patch("operaciones.services.calles.pedir_matriz", side_effect=matriz),
            patch("operaciones.services.calles.pedir_ruta", side_effect=_ruta_por_calles),
        ):
            respuesta = self.client.post(
                "/api/rutas/optimizar/",
                {
                    "cliente_id": self.cliente.id,
                    "fecha": self.hoy.isoformat(),
                    "destino_ids": [self.destino.id, self.destino_lejos.id],
                },
                format="json",
            )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data["destino_ids"], [self.destino_lejos.id, self.destino.id])
        self.assertEqual(len(capturados[0]), 3)
        self.assertNotIn(-12.046374, [punto[0] for punto in capturados[0]])
        self.assertGreater(len(respuesta.data["geometria_empresa"]["coordinates"]), 4)
        self.assertGreater(len(respuesta.data["geometria_cliente"]["coordinates"]), 2)
        self.assertNotEqual(
            respuesta.data["geometria_cliente"]["coordinates"][-1],
            respuesta.data["geometria_empresa"]["coordinates"][-1],
        )
        self.assertEqual(Ruta.objects.count(), 0)

    def test_fuera_de_lima_igual_calcula_la_calle(self):
        afuera = Destino.objects.create(
            cliente=self.cliente,
            fecha=self.hoy,
            codigo_externo="G-FUERA",
            tipo_servicio=Destino.TipoServicio.ENTREGA,
            documento_receptor="12345678",
            nombre_receptor="Ana",
            apellido_receptor="Diaz",
            telefono_receptor="999999999",
            direccion="Fuera de Lima",
            distrito="Cañete",
            latitud=-13.0,
            longitud=-76.4,
            motivo_servicio="Pedido",
            creado_por=self.admin,
        )
        with patch("operaciones.services.calles.pedir_ruta", side_effect=_ruta_por_calles):
            creada = self._crear_ruta([afuera.id])
        self.assertFalse(creada.data["dentro_de_lima"])
        self.assertGreater(len(creada.data["geometria_empresa"]["coordinates"]), 3)

    def _crear_ruta(self, destino_ids):
        self.autenticar(self.admin)
        respuesta = self.client.post(
            "/api/rutas/",
            {
                "cliente_id": self.cliente.id,
                "fecha": self.hoy.isoformat(),
                "conductor_id": self.conductor.id,
                "vehiculo_id": self.vehiculo.id,
                "destino_ids": destino_ids,
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        return respuesta


def _ruta_por_calles(puntos):
    tramos = []
    coordenadas = []
    for indice, (origen, destino) in enumerate(zip(puntos, puntos[1:])):
        linea = [
            [float(origen[1]), float(origen[0])],
            [float(origen[1]) + 0.01, float(origen[0]) - 0.01],
            [float(destino[1]), float(destino[0])],
        ]
        if coordenadas and linea[0] == coordenadas[-1]:
            coordenadas.extend(linea[1:])
        else:
            coordenadas.extend(linea)
        tramos.append(
            {
                "distance": 1000 * (indice + 1),
                "duration": 100 * (indice + 1),
                "geometria": {"type": "LineString", "coordinates": linea},
            }
        )
    return {
        "geometria": {"type": "LineString", "coordinates": coordenadas},
        "distance": sum(tramo["distance"] for tramo in tramos),
        "duration": sum(tramo["duration"] for tramo in tramos),
        "legs": tramos,
    }


class CoordenadaPrecisionTests(SimpleTestCase):
    def test_guarda_los_decimales_que_vienen_hasta_quince(self):
        self.assertEqual(coordenada_texto("-11.996963573604443"), "-11.996963573604443")
        self.assertEqual(coordenada_texto("-77.11872677728361"), "-77.11872677728361")
        self.assertEqual(coordenada_texto("-12.05"), "-12.05")
        self.assertEqual(coordenada_texto("-77.1187267772836114"), "-77.118726777283611")
