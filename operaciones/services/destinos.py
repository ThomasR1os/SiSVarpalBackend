from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalogos.models import Punto
from config.coordenadas import validar_coordenadas
from operaciones.models import Destino

from .fotos import subir_foto
from .geo import poligono_activo, punto_dentro


CAMPOS_RECEPTOR = (
    "documento_receptor",
    "nombre_receptor",
    "apellido_receptor",
    "telefono_receptor",
)


def _fecha_permitida(fecha):
    if fecha < timezone.localdate():
        raise ValidationError({"fecha": ["La fecha no puede ser anterior a hoy."]})


def _aplicar_sede(cliente, sede):
    if sede is None:
        raise ValidationError({"sede_id": ["Un traslado debe indicar la sede."]})
    if sede.cliente_id != cliente.id or not sede.es_sede or not sede.activo:
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


def preparar_destino(cliente, datos):
    if not str(datos.get("codigo_externo") or "").strip():
        raise ValidationError({"codigo_externo": ["El código es obligatorio."]})
    if not str(datos.get("motivo_servicio") or "").strip():
        raise ValidationError({"motivo_servicio": ["Indique por qué se hace el servicio."]})
    _fecha_permitida(datos["fecha"])
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


def crear_destino(*, cliente, datos, usuario):
    datos = preparar_destino(cliente, datos)
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
    if destino.estado != Destino.Estado.NO_INICIADO:
        raise ValidationError({"detail": "Solo se edita un destino que no ha iniciado."})
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
    return destino


def reprogramar_destino(destino, fecha):
    if destino.estado != Destino.Estado.NO_INICIADO:
        raise ValidationError({"fecha": ["Solo se reprograma un destino que no ha iniciado."]})
    _fecha_permitida(fecha)
    with transaction.atomic():
        _desvincular_si_cambia_fecha(destino, fecha)
        destino.fecha = fecha
        destino.save(update_fields=["fecha", "actualizado_en"])
    return destino


def validar_imagenes(archivos):
    from io import BytesIO

    from django.conf import settings
    from PIL import Image, UnidentifiedImageError

    if not archivos:
        raise ValidationError({"fotos": ["Se requiere al menos una foto."]})
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


def cerrar_destino(*, destino, resultado, motivo, observacion, fotos, usuario):
    from operaciones.models import Evidencia

    if destino.estado != Destino.Estado.EN_PROCESO:
        raise ValidationError({"detail": "Solo se cierra un destino que está en proceso."})
    if resultado not in {Destino.Estado.EXITOSO, Destino.Estado.FALLIDO}:
        raise ValidationError({"resultado": ["El resultado debe ser EXITOSO o FALLIDO."]})
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
        if asignacion is not None:
            asignacion.hora_llegada = asignacion.hora_llegada or ahora
            asignacion.hora_salida = ahora
            asignacion.save(update_fields=["hora_llegada", "hora_salida"])
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
