import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings


class MotorNoDisponible(Exception):
    pass


def pedir_ruta(puntos):
    return _pedir(puntos, con_geometria=True)


def pedir_duraciones(puntos):
    trazado = _pedir(puntos, con_geometria=False)
    if trazado is None:
        return None
    return [tramo["duration"] for tramo in trazado["legs"]]


def pedir_matriz(puntos):
    datos = _consultar("table", puntos, {"annotations": "distance"})
    if not isinstance(datos, dict) or datos.get("code") != "Ok":
        return None
    distancias = datos.get("distances")
    if not isinstance(distancias, list) or len(distancias) != len(puntos):
        return None
    return distancias


def _pedir(puntos, *, con_geometria):
    parametros = {
        "overview": "full" if con_geometria else "false",
        "steps": "true" if con_geometria else "false",
    }
    if con_geometria:
        parametros["geometries"] = "geojson"
    datos = _consultar("route", puntos, parametros)
    if not isinstance(datos, dict) or datos.get("code") != "Ok":
        return None
    rutas = datos.get("routes") or []
    if not rutas:
        return None
    ruta = rutas[0]
    crudos = ruta.get("legs") or []
    if len(crudos) != len(puntos) - 1:
        return None
    tramos = []
    for crudo in crudos:
        geometria = _geometria_de_pasos(crudo.get("steps") or []) if con_geometria else None
        tramos.append(
            {
                "distance": float(crudo.get("distance") or 0),
                "duration": float(crudo.get("duration") or 0),
                "geometria": geometria,
            }
        )
    geometria = None
    if con_geometria:
        cruda = ruta.get("geometry") or {}
        coordenadas = cruda.get("coordinates") if cruda.get("type") == "LineString" else None
        if coordenadas and len(coordenadas) >= 2:
            geometria = {"type": "LineString", "coordinates": coordenadas}
    return {
        "geometria": geometria,
        "distance": float(ruta.get("distance") or 0),
        "duration": float(ruta.get("duration") or 0),
        "legs": tramos,
    }


def _consultar(servicio, puntos, parametros):
    base = (settings.OSRM_BASE_URL or "").rstrip("/")
    if not base:
        raise MotorNoDisponible("OSRM_BASE_URL vacío")
    coordenadas = ";".join(f"{float(lng):.8f},{float(lat):.8f}" for lat, lng in puntos)
    consulta = dict(parametros)
    consulta["radiuses"] = ";".join(["unlimited"] * len(puntos))
    consulta["generate_hints"] = "false"
    url = f"{base}/{servicio}/v1/driving/{coordenadas}?{urllib.parse.urlencode(consulta)}"
    return _leer(url)


def _leer(url):
    solicitud = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "varpal-rutas"})
    try:
        with urllib.request.urlopen(solicitud, timeout=settings.OSRM_TIMEOUT_SEGUNDOS) as respuesta:
            return json.loads(respuesta.read().decode())
    except urllib.error.HTTPError as error:
        cuerpo = error.read().decode(errors="replace")
        try:
            datos = json.loads(cuerpo)
        except json.JSONDecodeError:
            datos = None
        if error.code >= 500 or datos is None:
            raise MotorNoDisponible(f"HTTP {error.code}") from error
        return datos
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        raise MotorNoDisponible(str(error)) from error


def _geometria_de_pasos(pasos):
    coordenadas = []
    for paso in pasos:
        geometria = paso.get("geometry") or {}
        puntos = geometria.get("coordinates") or []
        if coordenadas and puntos and puntos[0] == coordenadas[-1]:
            coordenadas.extend(puntos[1:])
        else:
            coordenadas.extend(puntos)
    if len(coordenadas) < 2:
        return None
    return {"type": "LineString", "coordinates": coordenadas}
