import json
import urllib.error
import urllib.request
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase, override_settings

from operaciones.services import calles
from operaciones.services.geo import construir_recorrido, haversine_metros, ordenar_por_cercania, segundos_de_viaje


def _punto(latitud, longitud):
    return SimpleNamespace(latitud=latitud, longitud=longitud)


def _respuesta(payload):
    class Respuesta:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return Respuesta()


@override_settings(OSRM_BASE_URL="http://osrm.local:5000", OSRM_TIMEOUT_SEGUNDOS=2)
class ContratoOsrmTests(SimpleTestCase):
    def test_pide_el_recorrido_completo_y_ajusta_el_punto_a_la_calle(self):
        capturado = {}

        def urlopen(solicitud, timeout=None):
            capturado["url"] = solicitud.full_url
            capturado["timeout"] = timeout
            return _respuesta(
                {
                    "code": "Ok",
                    "routes": [
                        {
                            "distance": 1500.4,
                            "duration": 210.2,
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[-77.09, -12.07], [-77.08, -12.08], [-77.05, -12.1]],
                            },
                            "legs": [
                                {
                                    "distance": 1500.4,
                                    "duration": 210.2,
                                    "steps": [
                                        {
                                            "geometry": {
                                                "type": "LineString",
                                                "coordinates": [[-77.09, -12.07], [-77.08, -12.08], [-77.05, -12.1]],
                                            }
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )

        with patch("operaciones.services.calles.urllib.request.urlopen", side_effect=urlopen):
            trazado = calles.pedir_ruta([(-12.07, -77.09), (-12.1, -77.05)])
        self.assertEqual(capturado["timeout"], 2)
        self.assertIn("/route/v1/driving/", capturado["url"])
        self.assertIn("-77.09000000,-12.07000000;-77.05000000,-12.10000000", capturado["url"])
        self.assertIn("overview=full", capturado["url"])
        self.assertIn("geometries=geojson", capturado["url"])
        self.assertIn("steps=true", capturado["url"])
        self.assertIn("radiuses=unlimited", capturado["url"])
        self.assertEqual(len(trazado["geometria"]["coordinates"]), 3)
        self.assertEqual(trazado["legs"][0]["duration"], 210.2)

    def test_un_punto_sin_calle_no_tumba_la_consulta(self):
        def urlopen(solicitud, timeout=None):
            raise HTTPError(
                solicitud.full_url,
                400,
                "Bad Request",
                {},
                BytesIO(json.dumps({"code": "NoSegment", "message": "No segment"}).encode()),
            )

        with patch("operaciones.services.calles.urllib.request.urlopen", side_effect=urlopen):
            self.assertIsNone(calles.pedir_ruta([(-12.07, -77.09), (-12.1, -77.05)]))

    def test_si_no_hay_conexion_avisa_que_el_motor_no_esta(self):
        def urlopen(solicitud, timeout=None):
            raise URLError("connection refused")

        with patch("operaciones.services.calles.urllib.request.urlopen", side_effect=urlopen):
            with self.assertRaises(calles.MotorNoDisponible):
                calles.pedir_ruta([(-12.07, -77.09), (-12.1, -77.05)])


@override_settings(OSRM_BASE_URL="http://osrm.local:5000", OSRM_TIMEOUT_SEGUNDOS=2)
class RecorridoTests(SimpleTestCase):
    def test_un_tramo_malo_no_borra_el_resto_del_recorrido(self):
        def pedir_ruta(puntos):
            if len(puntos) > 2:
                return None
            origen, destino = puntos
            if destino[0] < -12.5:
                return None
            return {
                "geometria": {
                    "type": "LineString",
                    "coordinates": [
                        [origen[1], origen[0]],
                        [origen[1] + 0.004, origen[0] - 0.004],
                        [destino[1], destino[0]],
                    ],
                },
                "distance": 800,
                "duration": 90,
                "legs": [
                    {
                        "distance": 800,
                        "duration": 90,
                        "geometria": {
                            "type": "LineString",
                            "coordinates": [
                                [origen[1], origen[0]],
                                [origen[1] + 0.004, origen[0] - 0.004],
                                [destino[1], destino[0]],
                            ],
                        },
                    }
                ],
            }

        origen = _punto(-12.07, -77.09)
        parada = _punto(-12.1, -77.05)
        base = _punto(-13.0, -76.4)
        with patch("operaciones.services.calles.pedir_ruta", side_effect=pedir_ruta):
            recorrido = construir_recorrido(origen, [parada], base)
        cliente = recorrido["geometria_cliente"]["coordinates"]
        empresa = recorrido["geometria_empresa"]["coordinates"]
        self.assertGreater(len(cliente), 2)
        self.assertIn([-77.086, -12.074], cliente)
        self.assertEqual(cliente[-1], [-77.05, -12.1])
        self.assertEqual(empresa[-1], [-76.4, -13.0])
        self.assertEqual(recorrido["distancia_cliente_metros"], 800)
        self.assertEqual(recorrido["duracion_cliente_segundos"], 90)
        self.assertGreater(recorrido["distancia_metros"], 800)

    def test_sin_motor_la_duracion_sale_de_la_recta(self):
        origen = _punto(-12.09, -77.05)
        parada = _punto(-12.1, -77.04)
        base = _punto(-12.046374, -77.042793)
        with patch("operaciones.services.calles.pedir_ruta", side_effect=calles.MotorNoDisponible("caído")):
            recorrido = construir_recorrido(origen, [parada], base)
        self.assertEqual(len(recorrido["geometria_cliente"]["coordinates"]), 2)
        self.assertEqual(len(recorrido["geometria_empresa"]["coordinates"]), 3)
        self.assertEqual(
            recorrido["duracion_segundos"],
            segundos_de_viaje(recorrido["distancia_metros"]),
        )
        self.assertLess(recorrido["distancia_cliente_metros"], recorrido["distancia_metros"])

    def test_el_orden_sale_de_la_matriz_y_no_de_la_recta(self):
        origen = _punto(-12.09, -77.05)
        cerca = _punto(-12.1, -77.04)
        lejos = _punto(-12.2, -77.02)

        def matriz(puntos):
            self.assertEqual(len(puntos), 3)
            return [
                [0, 9000, 100],
                [9000, 0, 400],
                [100, 400, 0],
            ]

        with patch("operaciones.services.calles.pedir_matriz", side_effect=matriz):
            orden = ordenar_por_cercania(origen, [cerca, lejos])
        self.assertEqual(orden, [lejos, cerca])


@override_settings(OSRM_BASE_URL="http://127.0.0.1:5000", OSRM_TIMEOUT_SEGUNDOS=8)
class LimaCallesTests(SimpleTestCase):
    def setUp(self):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5000/nearest/v1/driving/-77.08850000,-12.07550000?number=1",
                timeout=2,
            ) as respuesta:
                respuesta.read()
        except urllib.error.HTTPError:
            return
        except Exception as error:
            self.skipTest(f"OSRM local no está en marcha ({error})")

    def test_maranga_baja_por_la_marina_y_brigida_silva(self):
        origen = _punto(-12.0755, -77.0885)
        parada = _punto(-12.09, -77.086)
        base = _punto(-12.046374, -77.042793)
        recorrido = construir_recorrido(origen, [parada], base)
        cliente = recorrido["geometria_cliente"]["coordinates"]
        empresa = recorrido["geometria_empresa"]["coordinates"]
        recta = haversine_metros((origen.latitud, origen.longitud), (parada.latitud, parada.longitud))
        self.assertGreaterEqual(len(cliente), 40)
        self.assertGreater(len(empresa), len(cliente))
        self.assertGreater(recorrido["distancia_cliente_metros"], recta * 1.2)
        self.assertGreater(recorrido["distancia_metros"], recorrido["distancia_cliente_metros"])
        self.assertLess(haversine_metros((cliente[-1][1], cliente[-1][0]), (parada.latitud, parada.longitud)), 80)
        self.assertLess(haversine_metros((empresa[-1][1], empresa[-1][0]), (base.latitud, base.longitud)), 80)
        self.assertGreater(
            haversine_metros((cliente[-1][1], cliente[-1][0]), (base.latitud, base.longitud)),
            1000,
        )
        nombres = _nombres_de_calle(origen, parada)
        self.assertTrue(any("marina" in nombre.lower() for nombre in nombres), nombres)
        self.assertTrue(any("brigida silva" in nombre.lower() for nombre in nombres), nombres)


def _nombres_de_calle(origen, destino):
    url = (
        "http://127.0.0.1:5000/route/v1/driving/"
        f"{float(origen.longitud):.8f},{float(origen.latitud):.8f};"
        f"{float(destino.longitud):.8f},{float(destino.latitud):.8f}"
        "?overview=false&steps=true"
    )
    with urllib.request.urlopen(url, timeout=8) as respuesta:
        datos = json.loads(respuesta.read().decode())
    nombres = []
    for tramo in datos["routes"][0]["legs"]:
        for paso in tramo["steps"]:
            nombre = paso.get("name") or ""
            if nombre and (not nombres or nombres[-1] != nombre):
                nombres.append(nombre)
    return nombres
