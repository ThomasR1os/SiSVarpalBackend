import logging

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalogos.models import Punto
from config.coordenadas import validar_coordenadas
from operaciones.models import Destino

from .fotos import borrar_foto, subir_foto
from .geo import poligono_activo, punto_dentro

logger = logging.getLogger(__name__)


CAMPOS_RECEPTOR = (
    "documento_receptor",
    "nombre_receptor",
    "apellido_receptor",
    "telefono_receptor",
)


def _fecha_permitida(fecha, permitir_pasada=False):
    # Crear, editar y reprogramar aceptan una fecha anterior a hoy.
    del fecha, permitir_pasada


def _aplicar_sede(cliente, sede):
    if sede is None:
        raise ValidationError({"sede_id": ["Un traslado debe indicar la sede."]})
    if sede.cliente_id != cliente.id or not sede.activo or not (sede.es_sede or sede.es_principal):
        raise ValidationError({"sede_id": ["La sede no pertenece al cliente o no está activa."]})
    return {
        "sede": sede,
        "direccion": sede.direccion,
        "distrito": sede.distrito,
        "latitud": sede.latitud,
        "longitud": sede.longitud,
    }


def _validar_punto_servicio(datos):
    latitud, longitud = validar_coordenadas(datos.get("latitud"), datos.get("longitud"))
    faltantes = {}
    for campo in ("direccion", "distrito", *CAMPOS_RECEPTOR):
        if not str(datos.get(campo) or "").strip():
            faltantes[campo] = ["Este campo es obligatorio."]
    if faltantes:
        raise ValidationError(faltantes)
    datos["latitud"] = latitud
    datos["longitud"] = longitud
    datos["sede"] = None
    return datos


def preparar_destino(cliente, datos, permitir_fecha_pasada=False):
    if not str(datos.get("codigo_externo") or "").strip():
        raise ValidationError({"codigo_externo": ["El código es obligatorio."]})
    if not str(datos.get("motivo_servicio") or "").strip():
        raise ValidationError({"motivo_servicio": ["Indique por qué se hace el servicio."]})
    _fecha_permitida(datos["fecha"], permitir_pasada=permitir_fecha_pasada)
    tipo = datos["tipo_servicio"]
    if tipo not in Destino.TipoServicio.values:
        raise ValidationError({"tipo_servicio": ["Tipo de servicio no reconocido."]})
    if tipo == Destino.TipoServicio.TRASLADO:
        datos.update(_aplicar_sede(cliente, datos.get("sede")))
        datos.setdefault("documento_receptor", "")
        datos.setdefault("nombre_receptor", datos["sede"].nombre)
        datos.setdefault("apellido_receptor", "")
        datos.setdefault("telefono_receptor", "")
        if not datos["nombre_receptor"]:
            datos["nombre_receptor"] = datos["sede"].nombre
    else:
        _validar_punto_servicio(datos)
    datos["codigo_externo"] = str(datos["codigo_externo"]).strip()
    datos.setdefault("referencia", "")
    datos.setdefault("observaciones", "")
    datos.setdefault("datos_extra", {})
    return datos


def crear_destino(*, cliente, datos, usuario, permitir_fecha_pasada=False):
    datos = preparar_destino(cliente, datos, permitir_fecha_pasada=permitir_fecha_pasada)
    if Destino.objects.filter(cliente=cliente, codigo_externo=datos["codigo_externo"]).exists():
        raise ValidationError({"codigo_externo": ["Ya existe un destino con ese código para el cliente."]})
    return Destino.objects.create(
        cliente=cliente,
        creado_por=usuario,
        estado=Destino.Estado.NO_INICIADO,
        **datos,
    )


def _desvincular_si_cambia_fecha(destino, fecha):
    asignacion = getattr(destino, "asignacion", None)
    if asignacion is None or asignacion.ruta.fecha == fecha:
        return
    ruta = asignacion.ruta
    if ruta.estado not in {RutaEstado.BORRADOR, RutaEstado.NO_INICIADA}:
        raise ValidationError({"fecha": ["No se puede cambiar la fecha de un destino que ya está en una ruta iniciada."]})
    asignacion.delete()
    from .rutas import recalcular_ruta

    if not ruta.paradas.exists():
        ruta.estado = RutaEstado.CANCELADA
        ruta.save(update_fields=["estado", "actualizado_en"])
    else:
        recalcular_ruta(ruta)


class RutaEstado:
    BORRADOR = "BORRADOR"
    NO_INICIADA = "NO_INICIADA"


def actualizar_destino(destino, datos):
    if destino.estado not in {Destino.Estado.NO_INICIADO, Destino.Estado.EN_PROCESO}:
        raise ValidationError({"detail": "Solo se edita un destino pendiente o que está en proceso."})
    antes_lat, antes_lng = destino.latitud, destino.longitud
    antes_tipo = destino.tipo_servicio
    completo = {
        "codigo_externo": destino.codigo_externo,
        "fecha": destino.fecha,
        "tipo_servicio": destino.tipo_servicio,
        "sede": destino.sede,
        "documento_receptor": destino.documento_receptor,
        "nombre_receptor": destino.nombre_receptor,
        "apellido_receptor": destino.apellido_receptor,
        "telefono_receptor": destino.telefono_receptor,
        "direccion": destino.direccion,
        "distrito": destino.distrito,
        "referencia": destino.referencia,
        "latitud": destino.latitud,
        "longitud": destino.longitud,
        "motivo_servicio": destino.motivo_servicio,
        "observaciones": destino.observaciones,
        "datos_extra": destino.datos_extra,
    }
    completo.update(datos)
    completo = preparar_destino(destino.cliente, completo)
    if (
        Destino.objects.filter(cliente=destino.cliente, codigo_externo=completo["codigo_externo"])
        .exclude(pk=destino.pk)
        .exists()
    ):
        raise ValidationError({"codigo_externo": ["Ya existe un destino con ese código para el cliente."]})
    with transaction.atomic():
        _desvincular_si_cambia_fecha(destino, completo["fecha"])
        for campo, valor in completo.items():
            setattr(destino, campo, valor)
        destino.save()
    if (destino.latitud, destino.longitud) != (antes_lat, antes_lng) or destino.tipo_servicio != antes_tipo:
        _recalcular_ruta_del_destino(destino)
    return destino


def _recalcular_ruta_del_destino(destino):
    asignacion = getattr(destino, "asignacion", None)
    if asignacion is None:
        return
    from .rutas import recalcular_ruta

    try:
        recalcular_ruta(asignacion.ruta)
    except Exception:
        logger.exception(
            "No se pudo recalcular la ruta %s después de mover el destino %s.",
            asignacion.ruta_id,
            destino.pk,
        )


def reprogramar_destino(destino, fecha):
    if destino.estado != Destino.Estado.NO_INICIADO:
        raise ValidationError({"fecha": ["Solo se reprograma un destino que no ha iniciado."]})
    _fecha_permitida(fecha)
    with transaction.atomic():
        _desvincular_si_cambia_fecha(destino, fecha)
        destino.fecha = fecha
        destino.save(update_fields=["fecha", "actualizado_en"])
    return destino


def validar_imagenes(archivos, obligatorias=True):
    from io import BytesIO

    from django.conf import settings
    from PIL import Image, UnidentifiedImageError

    if not archivos:
        if obligatorias:
            raise ValidationError({"fotos": ["Se requiere al menos una foto."]})
        return
    if len(archivos) > settings.FOTOS_MAXIMAS_POR_CIERRE:
        raise ValidationError({"fotos": [f"Puede adjuntar hasta {settings.FOTOS_MAXIMAS_POR_CIERRE} fotos."]})
    for archivo in archivos:
        contenido = archivo.read()
        archivo.seek(0)
        try:
            imagen = Image.open(BytesIO(contenido))
            imagen.load()
        except (UnidentifiedImageError, OSError):
            raise ValidationError({"fotos": ["Cada archivo debe ser una imagen JPG, PNG o WEBP."]}) from None
        if imagen.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError({"fotos": ["Cada archivo debe ser una imagen JPG, PNG o WEBP."]})


def cerrar_destino(
    *,
    destino,
    resultado,
    motivo,
    observacion,
    fotos,
    usuario,
    hora_inicio_descarga,
    hora_fin_descarga,
):
    from operaciones.models import Evidencia

    if destino.estado not in {Destino.Estado.EN_PROCESO, Destino.Estado.PENDIENTE}:
        raise ValidationError({"detail": "Solo se cierra un destino en proceso o pendiente de evidencias."})
    if resultado not in {Destino.Estado.EXITOSO, Destino.Estado.FALLIDO}:
        raise ValidationError({"resultado": ["El resultado debe ser EXITOSO o FALLIDO."]})
    if hora_fin_descarga < hora_inicio_descarga:
        raise ValidationError(
            {"hora_fin_descarga": ["La hora de fin de descarga no puede ser anterior al inicio."]}
        )
    validar_imagenes(fotos)
    if resultado == Destino.Estado.FALLIDO:
        if motivo is None or not motivo.activo:
            raise ValidationError({"motivo_id": ["El motivo es obligatorio cuando el destino falla."]})
    else:
        motivo = None
    ahora = timezone.now()
    with transaction.atomic():
        destino.estado = resultado
        destino.motivo = motivo
        destino.observacion_cierre = observacion or ""
        destino.save(update_fields=["estado", "motivo", "observacion_cierre", "actualizado_en"])
        for foto in fotos:
            Evidencia.objects.create(
                destino=destino,
                subido_por=usuario,
                archivo=subir_foto(foto, destino.id),
            )
        asignacion = getattr(destino, "asignacion", None)
        if asignacion is None:
            raise ValidationError({"detail": "El destino no está asignado a una ruta."})
        asignacion.hora_llegada = asignacion.hora_llegada or ahora
        asignacion.hora_salida = ahora
        asignacion.hora_inicio_descarga = hora_inicio_descarga
        asignacion.hora_fin_descarga = hora_fin_descarga
        asignacion.save(
            update_fields=[
                "hora_llegada",
                "hora_salida",
                "hora_inicio_descarga",
                "hora_fin_descarga",
            ]
        )
    if asignacion is not None:
        try:
            from .rutas import reordenar_segun_entregas

            reordenar_segun_entregas(asignacion.ruta)
        except Exception:
            logger.exception("No se pudo reordenar la ruta %s tras cerrar el destino %s.", asignacion.ruta_id, destino.pk)
    return destino


def georeferenciar_destino(destino, latitud, longitud):
    if destino.estado not in {Destino.Estado.EN_PROCESO, Destino.Estado.PENDIENTE}:
        raise ValidationError({"detail": "Solo se georeferencia un destino que está en proceso."})
    latitud, longitud = validar_coordenadas(latitud, longitud)
    destino.latitud = latitud
    destino.longitud = longitud
    destino.save(update_fields=["latitud", "longitud", "actualizado_en"])
    _recalcular_ruta_del_destino(destino)
    return destino


def corregir_cierre(*, destino, resultado, motivo, observacion, fotos, eliminar_ids, usuario):
    from django.conf import settings

    from operaciones.models import Evidencia

    if destino.estado not in {Destino.Estado.EXITOSO, Destino.Estado.FALLIDO, Destino.Estado.PENDIENTE}:
        raise ValidationError({"detail": "Solo se corrige un destino cerrado o pendiente de evidencias."})
    if resultado not in {Destino.Estado.EXITOSO, Destino.Estado.FALLIDO, Destino.Estado.PENDIENTE}:
        raise ValidationError({"resultado": ["El resultado debe ser EXITOSO, FALLIDO o PENDIENTE."]})
    if resultado == Destino.Estado.FALLIDO:
        if motivo is None or not motivo.activo:
            raise ValidationError({"motivo_id": ["Seleccione un motivo activo."]})
    else:
        motivo = None
    validar_imagenes(fotos, obligatorias=False)
    actuales = list(destino.evidencias.all())
    ids_actuales = {evidencia.id for evidencia in actuales}
    try:
        quitar = {int(valor) for valor in eliminar_ids}
    except (TypeError, ValueError):
        raise ValidationError({"eliminar": ["Identificador de foto inválido."]}) from None
    ajenos = quitar - ids_actuales
    if ajenos:
        raise ValidationError({"eliminar": ["Hay fotos que no pertenecen a este destino."]})
    quedan = len(actuales) - len(quitar) + len(fotos)
    if resultado != Destino.Estado.PENDIENTE and quedan < 1:
        raise ValidationError({"fotos": ["Debe quedar al menos una evidencia."]})
    if quedan > settings.FOTOS_MAXIMAS_POR_CIERRE:
        raise ValidationError({"fotos": [f"Puede dejar hasta {settings.FOTOS_MAXIMAS_POR_CIERRE} fotos."]})
    a_borrar = [evidencia.archivo for evidencia in actuales if evidencia.id in quitar]
    with transaction.atomic():
        destino.estado = resultado
        destino.motivo = motivo
        destino.observacion_cierre = observacion or ""
        destino.save(update_fields=["estado", "motivo", "observacion_cierre", "actualizado_en"])
        if quitar:
            Evidencia.objects.filter(destino=destino, id__in=quitar).delete()
        for foto in fotos:
            Evidencia.objects.create(destino=destino, subido_por=usuario, archivo=subir_foto(foto, destino.id))
    for url in a_borrar:
        borrar_foto(url)
    return destino


def dentro_de_lima_puntos(puntos):
    poligono = poligono_activo()
    return all(punto_dentro(lat, lng, poligono) for lat, lng in puntos)


def base_final_empresa():
    punto = Punto.objects.filter(cliente__isnull=True, es_principal=True, es_base_final=True, activo=True).first()
    if punto is None:
        raise ValidationError({"base_final_id": ["Registre la dirección principal de la empresa antes de armar rutas."]})
    return punto


def base_origen_cliente(cliente):
    punto = Punto.objects.filter(cliente=cliente, es_principal=True, es_base_origen=True, activo=True).first()
    if punto is None:
        raise ValidationError({"base_origen_id": ["El cliente no tiene dirección principal."]})
    return punto
