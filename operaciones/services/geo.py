import logging
import math
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from shapely.geometry import Point, Polygon

from catalogos.models import Geocerca

from . import calles


logger = logging.getLogger(__name__)


def haversine_metros(origen, destino):
    lat1, lon1 = map(math.radians, origen)
    lat2, lon2 = map(math.radians, destino)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    altura = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(altura))


def segundos_de_viaje(metros):
    if metros <= 0:
        return 0
    return int(metros / (settings.VELOCIDAD_CIUDAD_KMH * 1000) * 3600)


def linea(puntos):
    return {
        "type": "LineString",
        "coordinates": [[float(lng), float(lat)] for lat, lng in puntos],
    }


def distancia_de_linea(geometria):
    coordenadas = (geometria or {}).get("coordinates") or []
    if len(coordenadas) < 2:
        return 0
    total = 0
    for inicio, fin in zip(coordenadas, coordenadas[1:]):
        total += haversine_metros((inicio[1], inicio[0]), (fin[1], fin[0]))
    return int(total)


def poligono_activo():
    geocerca = Geocerca.objects.filter(activa=True).order_by("-id").first()
    if geocerca is None or not geocerca.poligono:
        return None
    return Polygon([(punto[0], punto[1]) for punto in geocerca.poligono])


def punto_dentro(latitud, longitud, poligono):
    if poligono is None:
        return False
    return bool(poligono.covers(Point(float(longitud), float(latitud))))


def _coordenada(punto):
    return (float(punto.latitud), float(punto.longitud))


def _entero(valor):
    return max(0, int(round(valor)))


def _geometria_valida(geometria):
    return (
        isinstance(geometria, dict)
        and geometria.get("type") == "LineString"
        and len(geometria.get("coordinates") or []) >= 2
    )


def _unir_lineas(geometrias):
    coordenadas = []
    for geometria in geometrias:
        if not _geometria_valida(geometria):
            return None
        puntos = geometria["coordinates"]
        if coordenadas and puntos[0] == coordenadas[-1]:
            coordenadas.extend(puntos[1:])
        else:
            coordenadas.extend(puntos)
    if len(coordenadas) < 2:
        return None
    return {"type": "LineString", "coordinates": coordenadas}


def _tramo_recto(origen, destino):
    metros = haversine_metros(origen, destino)
    return {
        "distance": metros,
        "duration": float(segundos_de_viaje(metros)),
        "geometria": linea([origen, destino]),
    }


def _recorrido_recto(puntos_cliente, puntos_empresa):
    geometria_cliente = linea(puntos_cliente)
    geometria_empresa = linea(puntos_empresa)
    distancia_cliente = distancia_de_linea(geometria_cliente)
    distancia = distancia_de_linea(geometria_empresa)
    return {
        "geometria_cliente": geometria_cliente,
        "geometria_empresa": geometria_empresa,
        "distancia_metros": distancia,
        "duracion_segundos": segundos_de_viaje(distancia),
        "distancia_cliente_metros": distancia_cliente,
        "duracion_cliente_segundos": segundos_de_viaje(distancia_cliente),
    }


def trazar_calles(puntos):
    puntos = [(float(lat), float(lng)) for lat, lng in puntos]
    if len(puntos) < 2 or not settings.OSRM_BASE_URL:
        return None
    try:
        trazado = calles.pedir_ruta(puntos)
    except calles.MotorNoDisponible as error:
        logger.warning("El motor de rutas no respondió (%s). Se usa la recta de respaldo.", error)
        return None
    if trazado is None:
        trazado = _trazar_por_tramos(puntos)
    if trazado is None:
        return None
    return _completar_geometrias(puntos, trazado)


def _trazar_por_tramos(puntos):
    logger.warning("El motor de rutas no pudo trazar todos los puntos juntos. Se enruta tramo a tramo.")
    tramos = []
    for origen, destino in zip(puntos, puntos[1:]):
        try:
            tramo = calles.pedir_ruta([origen, destino])
        except calles.MotorNoDisponible as error:
            logger.warning("El motor de rutas no respondió (%s). Se usa la recta de respaldo.", error)
            return None
        if tramo is None or not tramo["legs"]:
            tramos.append(_tramo_recto(origen, destino))
            continue
        tramos.append(tramo["legs"][0])
    geometria = _unir_lineas([tramo["geometria"] for tramo in tramos])
    if geometria is None:
        geometria = linea(puntos)
    return {
        "geometria": geometria,
        "distance": sum(tramo["distance"] for tramo in tramos),
        "duration": sum(tramo["duration"] for tramo in tramos),
        "legs": tramos,
    }


def _completar_geometrias(puntos, trazado):
    tramos = trazado.get("legs") or []
    if len(tramos) != len(puntos) - 1:
        return None
    for indice, tramo in enumerate(tramos):
        if not _geometria_valida(tramo.get("geometria")):
            tramo["geometria"] = linea([puntos[indice], puntos[indice + 1]])
    if not _geometria_valida(trazado.get("geometria")):
        trazado["geometria"] = _unir_lineas([tramo["geometria"] for tramo in tramos])
    if not _geometria_valida(trazado.get("geometria")):
        return None
    return trazado


def _matriz_por_calle(puntos):
    if not settings.OSRM_BASE_URL:
        return None
    try:
        matriz = calles.pedir_matriz(puntos)
    except calles.MotorNoDisponible as error:
        logger.warning(
            "El motor de rutas no respondió al ordenar (%s). Se usa la distancia en línea recta.",
            error,
        )
        return None
    if matriz is None:
        logger.warning("El motor de rutas no devolvió distancias por calle. Se usa la distancia en línea recta.")
    return matriz


def _costo_calle(matriz, puntos, desde, hasta):
    if matriz is not None and desde < len(matriz):
        fila = matriz[desde]
        if fila is not None and hasta < len(fila) and fila[hasta] is not None:
            return fila[hasta]
    return haversine_metros(puntos[desde], puntos[hasta])


def ordenar_por_cercania(origen, destinos):
    if not destinos:
        return []
    puntos = [_coordenada(origen)] + [_coordenada(destino) for destino in destinos]
    matriz = _matriz_por_calle(puntos)
    pendientes = list(range(len(destinos)))
    actual = 0
    orden = []
    while pendientes:
        siguiente = min(pendientes, key=lambda indice: _costo_calle(matriz, puntos, actual, indice + 1))
        orden.append(destinos[siguiente])
        actual = siguiente + 1
        pendientes.remove(siguiente)
    return orden


def construir_recorrido(origen, destinos, base_final=None):
    puntos_cliente = [_coordenada(origen)]
    puntos_cliente.extend(_coordenada(destino) for destino in destinos)
    puntos_empresa = list(puntos_cliente)
    if base_final is not None:
        puntos_empresa.append(_coordenada(base_final))
    recta = _recorrido_recto(puntos_cliente, puntos_empresa)
    trazado = trazar_calles(puntos_empresa)
    if trazado is None:
        return recta
    tramos_cliente = trazado["legs"][: len(puntos_cliente) - 1]
    geometria_cliente = _unir_lineas([tramo["geometria"] for tramo in tramos_cliente])
    if geometria_cliente is None:
        return recta
    return {
        "geometria_cliente": geometria_cliente,
        "geometria_empresa": trazado["geometria"],
        "distancia_metros": _entero(sum(tramo["distance"] for tramo in trazado["legs"])),
        "duracion_segundos": _entero(sum(tramo["duration"] for tramo in trazado["legs"])),
        "distancia_cliente_metros": _entero(sum(tramo["distance"] for tramo in tramos_cliente)),
        "duracion_cliente_segundos": _entero(sum(tramo["duration"] for tramo in tramos_cliente)),
    }


def _duraciones_por_calle(puntos):
    if len(puntos) < 2 or not settings.OSRM_BASE_URL:
        return None
    try:
        duraciones = calles.pedir_duraciones(puntos)
    except calles.MotorNoDisponible as error:
        logger.warning(
            "El motor de rutas no respondió al estimar horas (%s). Se usa la recta de respaldo.",
            error,
        )
        return None
    if not duraciones or len(duraciones) != len(puntos) - 1:
        return None
    return [_entero(valor) for valor in duraciones]


def estimar_horas(ruta):
    if ruta.iniciada_en is None:
        ruta.paradas.update(hora_estimada=None)
        return
    paradas = list(ruta.paradas.select_related("destino").order_by("orden"))
    puntos = [_coordenada(ruta.base_origen)] + [_coordenada(parada.destino) for parada in paradas]
    duraciones = _duraciones_por_calle(puntos)
    actual = puntos[0]
    acumulado = ruta.iniciada_en
    if timezone.is_naive(acumulado):
        acumulado = timezone.make_aware(acumulado, timezone.get_current_timezone())
    for indice, parada in enumerate(paradas):
        if duraciones is not None and indice < len(duraciones):
            segundos = duraciones[indice]
        else:
            segundos = segundos_de_viaje(haversine_metros(actual, puntos[indice + 1]))
        acumulado += timedelta(seconds=segundos)
        parada.hora_estimada = acumulado
        parada.save(update_fields=["hora_estimada"])
        actual = puntos[indice + 1]
