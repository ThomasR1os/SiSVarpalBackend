from catalogos.models import Punto
from operaciones.models import Ruta


def sincronizar_punto_cliente(cliente):
    punto = Punto.objects.filter(cliente=cliente, es_principal=True).first()
    if punto is None:
        punto = Punto(cliente=cliente, es_principal=True, codigo="BASE-PRINCIPAL")
    punto.nombre = cliente.razon_social
    punto.direccion = cliente.direccion_principal
    punto.distrito = cliente.distrito
    punto.latitud = cliente.latitud
    punto.longitud = cliente.longitud
    punto.es_base_origen = True
    punto.es_principal = True
    punto.es_base_final = False
    punto.activo = cliente.activo
    punto.save()
    _recalcular(punto)
    return punto


def sincronizar_punto_empresa(empresa):
    punto = Punto.objects.filter(cliente__isnull=True, es_principal=True).first()
    if punto is None:
        punto = Punto(cliente=None, es_principal=True, codigo="BASE-PRINCIPAL")
    punto.nombre = empresa.razon_social
    punto.direccion = empresa.direccion_principal
    punto.distrito = empresa.distrito
    punto.latitud = empresa.latitud
    punto.longitud = empresa.longitud
    punto.es_base_final = True
    punto.es_principal = True
    punto.es_base_origen = False
    punto.es_sede = False
    punto.activo = True
    punto.save()
    _recalcular(punto)
    return punto


def _recalcular(punto):
    from operaciones.services.rutas import recalcular_rutas_de_punto

    if Ruta.objects.filter(base_origen=punto).exists() or Ruta.objects.filter(base_final=punto).exists():
        recalcular_rutas_de_punto(punto)


def ruc_valido(ruc):
    return isinstance(ruc, str) and len(ruc) == 11 and ruc.isdigit()
