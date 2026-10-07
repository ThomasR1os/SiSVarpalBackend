from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from operaciones.models import Destino, Notificacion, Posicion, Ruta, RutaAuxiliar, RutaDestino
from usuarios.models import Rol, Usuario

from config.coordenadas import coordenada_texto

from .destinos import base_final_empresa, base_origen_cliente, dentro_de_lima_puntos
from .geo import construir_recorrido, estimar_horas, ordenar_por_cercania


ESTADOS_EDITABLES = {Ruta.Estado.BORRADOR, Ruta.Estado.NO_INICIADA}


def rutas_visibles(usuario):
    qs = Ruta.objects.select_related(
        "cliente", "conductor", "vehiculo", "base_origen", "base_final"
    ).prefetch_related("auxiliares__usuario", "paradas__destino")
    rol = usuario.rol_nombre
    if rol == Rol.Nombre.ADMINISTRADOR:
        return qs
    if rol == Rol.Nombre.CLIENTE:
        return qs.filter(cliente_id=usuario.cliente_id).exclude(estado=Ruta.Estado.BORRADOR)
    if rol == Rol.Nombre.CONDUCTOR:
        return qs.filter(conductor=usuario).exclude(estado=Ruta.Estado.BORRADOR)
    if rol == Rol.Nombre.AUXILIAR:
        return qs.filter(auxiliares__usuario=usuario).exclude(estado=Ruta.Estado.BORRADOR).distinct()
    return qs.none()


def destinos_visibles(usuario):
    qs = Destino.objects.select_related("cliente", "sede", "motivo", "asignacion")
    rol = usuario.rol_nombre
    if rol == Rol.Nombre.ADMINISTRADOR:
        return qs
    if rol == Rol.Nombre.CLIENTE:
        return qs.filter(cliente_id=usuario.cliente_id)
    if rol == Rol.Nombre.CONDUCTOR:
        return qs.filter(asignacion__ruta__conductor=usuario)
    if rol == Rol.Nombre.AUXILIAR:
        return qs.filter(asignacion__ruta__auxiliares__usuario=usuario).distinct()
    return qs.none()


def puede_operar_parada(usuario, destino):
    if usuario.rol_nombre == Rol.Nombre.ADMINISTRADOR:
        return True
    asignacion = getattr(destino, "asignacion", None)
    if asignacion is None:
        return False
    ruta = asignacion.ruta
    if usuario.rol_nombre == Rol.Nombre.CONDUCTOR and ruta.conductor_id == usuario.id:
        return True
    if usuario.rol_nombre == Rol.Nombre.AUXILIAR and ruta.auxiliares.filter(usuario=usuario).exists():
        return True
    return False


def _validar_bases(cliente, base_origen, base_final):
    if base_origen is None:
        base_origen = base_origen_cliente(cliente)
    if base_origen.cliente_id != cliente.id or not base_origen.es_base_origen or not base_origen.activo:
        raise ValidationError({"base_origen_id": ["La base de origen debe ser una base activa del cliente."]})
    if base_final is None:
        base_final = base_final_empresa()
    if base_final.cliente_id is not None or not base_final.es_base_final or not base_final.activo:
        raise ValidationError({"base_final_id": ["La base final debe ser una base activa de la empresa."]})
    return base_origen, base_final


def _validar_destinos(cliente, fecha, destinos, ruta=None):
    if not destinos:
        raise ValidationError({"destino_ids": ["La ruta necesita al menos un destino."]})
    if len({destino.id for destino in destinos}) != len(destinos):
        raise ValidationError({"destino_ids": ["Hay destinos repetidos."]})
    ocupados = RutaDestino.objects.filter(destino__in=destinos)
    if ruta is not None:
        ocupados = ocupados.exclude(ruta=ruta)
    if ocupados.exists():
        raise ValidationError({"destino_ids": ["Uno o más destinos ya pertenecen a otra ruta."]})
    for destino in destinos:
        if destino.cliente_id != cliente.id or destino.fecha != fecha:
            raise ValidationError(
                {"destino_ids": ["Los destinos deben ser del mismo cliente y de la misma fecha de la ruta."]}
            )
        if destino.estado != Destino.Estado.NO_INICIADO:
            raise ValidationError({"destino_ids": ["Solo se asignan destinos que no han iniciado."]})
    return list(destinos)


def _validar_auxiliares(auxiliares, conductor):
    from django.conf import settings

    if len(auxiliares) > settings.AUXILIARES_MAXIMOS:
        raise ValidationError({"auxiliar_ids": [f"Una ruta admite hasta {settings.AUXILIARES_MAXIMOS} auxiliares."]})
    if len({usuario.id for usuario in auxiliares}) != len(auxiliares):
        raise ValidationError({"auxiliar_ids": ["Hay auxiliares repetidos."]})
    for usuario in auxiliares:
        if usuario.rol_nombre != Rol.Nombre.AUXILIAR or not usuario.is_active:
            raise ValidationError({"auxiliar_ids": ["Cada auxiliar debe ser un usuario auxiliar activo."]})
        if usuario.id == conductor.id:
            raise ValidationError({"auxiliar_ids": ["El conductor no puede ir también como auxiliar."]})


def _validar_fecha(fecha):
    if fecha < timezone.localdate():
        raise ValidationError({"fecha": ["Solo se arman rutas para hoy o para los próximos días."]})


def _reemplazar_paradas(ruta, destinos):
    actuales = {parada.destino_id: parada for parada in ruta.paradas.all()}
    for destino_id, parada in list(actuales.items()):
        if destino_id not in {destino.id for destino in destinos}:
            parada.delete()
            actuales.pop(destino_id)
    for indice, parada in enumerate(ruta.paradas.all(), start=1):
        parada.orden = 10000 + indice
        parada.save(update_fields=["orden"])
    for orden, destino in enumerate(destinos, start=1):
        parada = actuales.get(destino.id)
        if parada is None:
            RutaDestino.objects.create(ruta=ruta, destino=destino, orden=orden)
        else:
            parada.orden = orden
            parada.save(update_fields=["orden"])


def recalcular_ruta(ruta):
    ruta = Ruta.objects.select_related("base_origen", "base_final").get(pk=ruta.pk)
    destinos = [parada.destino for parada in ruta.paradas.select_related("destino").order_by("orden")]
    recorrido = construir_recorrido(ruta.base_origen, destinos, ruta.base_final)
    puntos = [(ruta.base_origen.latitud, ruta.base_origen.longitud)]
    puntos.extend((destino.latitud, destino.longitud) for destino in destinos)
    puntos.append((ruta.base_final.latitud, ruta.base_final.longitud))
    ruta.geometria_cliente = recorrido["geometria_cliente"]
    ruta.geometria_empresa = recorrido["geometria_empresa"]
    ruta.distancia_metros = recorrido["distancia_metros"]
    ruta.duracion_segundos = recorrido["duracion_segundos"]
    ruta.distancia_cliente_metros = recorrido["distancia_cliente_metros"]
    ruta.duracion_cliente_segundos = recorrido["duracion_cliente_segundos"]
    ruta.dentro_de_lima = dentro_de_lima_puntos(puntos)
    ruta.save(
        update_fields=[
            "geometria_cliente",
            "geometria_empresa",
            "distancia_metros",
            "duracion_segundos",
            "distancia_cliente_metros",
            "duracion_cliente_segundos",
            "dentro_de_lima",
            "actualizado_en",
        ]
    )
    estimar_horas(ruta)
    return ruta


def proponer_ruta(*, cliente, fecha, base_origen, base_final, destinos):
    _validar_fecha(fecha)
    base_origen, base_final = _validar_bases(cliente, base_origen, base_final)
    destinos = _validar_destinos(cliente, fecha, destinos)
    ordenados = ordenar_por_cercania(base_origen, destinos)
    recorrido = construir_recorrido(base_origen, ordenados, base_final)
    puntos = [(base_origen.latitud, base_origen.longitud)]
    puntos.extend((destino.latitud, destino.longitud) for destino in ordenados)
    puntos.append((base_final.latitud, base_final.longitud))
    return {
        "destino_ids": [destino.id for destino in ordenados],
        "paradas": [
            {
                "orden": orden,
                "destino_id": destino.id,
                "codigo_externo": destino.codigo_externo,
                "direccion": destino.direccion,
                "distrito": destino.distrito,
                "latitud": coordenada_texto(destino.latitud),
                "longitud": coordenada_texto(destino.longitud),
            }
            for orden, destino in enumerate(ordenados, start=1)
        ],
        "distancia_metros": recorrido["distancia_metros"],
        "duracion_segundos": recorrido["duracion_segundos"],
        "geometria_empresa": recorrido["geometria_empresa"],
        "geometria_cliente": recorrido["geometria_cliente"],
        "dentro_de_lima": dentro_de_lima_puntos(puntos),
    }


@transaction.atomic
def crear_ruta(*, cliente, fecha, conductor, vehiculo, auxiliares, base_origen, base_final, destinos, creado_por, optimizar=False):
    _validar_fecha(fecha)
    if not cliente.activo:
        raise ValidationError({"cliente_id": ["El cliente está inactivo."]})
    if conductor.rol_nombre != Rol.Nombre.CONDUCTOR or not conductor.is_active:
        raise ValidationError({"conductor_id": ["El conductor debe ser un usuario conductor activo."]})
    if not vehiculo.activo:
        raise ValidationError({"vehiculo_id": ["El vehículo está inactivo."]})
    _validar_auxiliares(auxiliares, conductor)
    base_origen, base_final = _validar_bases(cliente, base_origen, base_final)
    destinos = _validar_destinos(cliente, fecha, destinos)
    if optimizar:
        destinos = ordenar_por_cercania(base_origen, destinos)
    ruta = Ruta.objects.create(
        cliente=cliente,
        fecha=fecha,
        conductor=conductor,
        vehiculo=vehiculo,
        base_origen=base_origen,
        base_final=base_final,
        estado=Ruta.Estado.BORRADOR,
        creado_por=creado_por,
    )
    RutaAuxiliar.objects.bulk_create(
        [RutaAuxiliar(ruta=ruta, usuario=usuario) for usuario in auxiliares]
    )
    RutaDestino.objects.bulk_create(
        [RutaDestino(ruta=ruta, destino=destino, orden=orden) for orden, destino in enumerate(destinos, start=1)]
    )
    return recalcular_ruta(ruta)


@transaction.atomic
def actualizar_ruta(ruta, datos):
    if ruta.estado not in ESTADOS_EDITABLES:
        raise ValidationError({"detail": "Solo se edita una ruta que no ha iniciado."})
    cliente = ruta.cliente
    fecha = datos.get("fecha", ruta.fecha)
    conductor = datos.get("conductor", ruta.conductor)
    vehiculo = datos.get("vehiculo", ruta.vehiculo)
    auxiliares = datos.get("auxiliares")
    base_origen = datos.get("base_origen", ruta.base_origen)
    base_final = datos.get("base_final", ruta.base_final)
    destinos = datos.get("destinos")
    optimizar = datos.get("optimizar", False)
    _validar_fecha(fecha)
    if conductor.rol_nombre != Rol.Nombre.CONDUCTOR or not conductor.is_active:
        raise ValidationError({"conductor_id": ["El conductor debe ser un usuario conductor activo."]})
    if not vehiculo.activo:
        raise ValidationError({"vehiculo_id": ["El vehículo está inactivo."]})
    if auxiliares is not None:
        _validar_auxiliares(auxiliares, conductor)
    origen_anterior = ruta.base_origen_id
    final_anterior = ruta.base_final_id
    orden_anterior = list(ruta.paradas.order_by("orden").values_list("destino_id", flat=True))
    pidio_destinos = "destinos" in datos
    base_origen, base_final = _validar_bases(cliente, base_origen, base_final)
    if destinos is None:
        destinos = [parada.destino for parada in ruta.paradas.select_related("destino").order_by("orden")]
    else:
        destinos = _validar_destinos(cliente, fecha, destinos, ruta=ruta)
    if optimizar:
        destinos = ordenar_por_cercania(base_origen, destinos)
    if any(destino.fecha != fecha for destino in destinos):
        raise ValidationError(
            {"fecha": ["Para cambiar la fecha de la ruta, todos sus destinos deben tener esa fecha."]}
        )
    ruta.fecha = fecha
    ruta.conductor = conductor
    ruta.vehiculo = vehiculo
    ruta.base_origen = base_origen
    ruta.base_final = base_final
    ruta.save()
    if auxiliares is not None:
        ruta.auxiliares.all().delete()
        RutaAuxiliar.objects.bulk_create(
            [RutaAuxiliar(ruta=ruta, usuario=usuario) for usuario in auxiliares]
        )
    _reemplazar_paradas(ruta, destinos)
    orden_nuevo = [destino.id for destino in destinos]
    cambia_trazado = (
        bool(optimizar)
        or base_origen.id != origen_anterior
        or base_final.id != final_anterior
        or (pidio_destinos and orden_nuevo != orden_anterior)
    )
    if not cambia_trazado:
        return ruta
    return recalcular_ruta(ruta)


def aplicar_orden(ruta, destino_ids):
    if ruta.estado not in ESTADOS_EDITABLES:
        raise ValidationError({"detail": "Solo se reordena una ruta que no ha iniciado."})
    paradas = list(ruta.paradas.all())
    actuales = {parada.destino_id: parada for parada in paradas}
    if set(actuales) != set(destino_ids) or len(destino_ids) != len(set(destino_ids)):
        raise ValidationError({"destino_ids": ["El orden debe incluir exactamente las paradas de la ruta, sin repetir."]})
    with transaction.atomic():
        for indice, parada in enumerate(paradas, start=1):
            parada.orden = 10000 + indice
            parada.save(update_fields=["orden"])
        for orden, destino_id in enumerate(destino_ids, start=1):
            parada = actuales[destino_id]
            parada.orden = orden
            parada.save(update_fields=["orden"])
    return recalcular_ruta(ruta)


def confirmar_ruta(ruta):
    if ruta.estado != Ruta.Estado.BORRADOR:
        raise ValidationError({"detail": "Solo se confirma una ruta en borrador."})
    if not ruta.paradas.exists():
        raise ValidationError({"detail": "La ruta no tiene destinos."})
    ruta.estado = Ruta.Estado.NO_INICIADA
    ruta.save(update_fields=["estado", "actualizado_en"])
    return ruta


@transaction.atomic
def iniciar_ruta(ruta, usuario):
    ruta = Ruta.objects.select_for_update().get(pk=ruta.pk)
    if usuario.rol_nombre != Rol.Nombre.CONDUCTOR or ruta.conductor_id != usuario.id:
        raise PermissionDenied("Solo el conductor asignado puede iniciar la ruta.")
    if ruta.estado != Ruta.Estado.NO_INICIADA:
        raise ValidationError({"detail": "Solo se inicia una ruta confirmada que aún no ha empezado."})
    if Ruta.objects.filter(conductor=usuario, estado=Ruta.Estado.EN_PROCESO).exists():
        raise ValidationError({"detail": "Ya tiene una ruta en proceso. Debe llegar a la base antes de iniciar otra."})
    ahora = timezone.now()
    ruta.estado = Ruta.Estado.EN_PROCESO
    ruta.iniciada_en = ahora
    ruta.save(update_fields=["estado", "iniciada_en", "actualizado_en"])
    Destino.objects.filter(asignacion__ruta=ruta, estado=Destino.Estado.NO_INICIADO).update(
        estado=Destino.Estado.EN_PROCESO
    )
    estimar_horas(ruta)
    admins = Usuario.objects.filter(rol__nombre=Rol.Nombre.ADMINISTRADOR, is_active=True)
    Notificacion.objects.bulk_create(
        [
            Notificacion(
                usuario=admin,
                ruta=ruta,
                tipo=Notificacion.Tipo.RUTA_INICIADA,
                titulo="Ruta iniciada",
                cuerpo=f"{usuario.nombre} {usuario.apellido} inició la ruta {ruta.id} del {ruta.fecha:%d/%m/%Y}.",
            )
            for admin in admins
        ]
    )
    return ruta


def confirmar_llegada(ruta, usuario):
    if ruta.estado != Ruta.Estado.EN_PROCESO:
        raise ValidationError({"detail": "La ruta no está en proceso."})
    es_conductor = usuario.rol_nombre == Rol.Nombre.CONDUCTOR and ruta.conductor_id == usuario.id
    es_admin = usuario.rol_nombre == Rol.Nombre.ADMINISTRADOR
    if not (es_conductor or es_admin):
        raise PermissionDenied("Solo el conductor asignado puede confirmar la llegada a la base.")
    estados = list(ruta.paradas.values_list("destino__estado", flat=True))
    if not estados or any(estado not in {Destino.Estado.EXITOSO, Destino.Estado.FALLIDO} for estado in estados):
        raise ValidationError({"detail": "Aún hay paradas sin cerrar."})
    ahora = timezone.now()
    ruta.estado = Ruta.Estado.FINALIZADA
    ruta.llegada_base_en = ahora
    ruta.finalizada_en = ahora
    ruta.save(update_fields=["estado", "llegada_base_en", "finalizada_en", "actualizado_en"])
    return ruta


@transaction.atomic
def cancelar_ruta(ruta):
    if ruta.estado not in ESTADOS_EDITABLES:
        raise ValidationError({"detail": "Solo se cancela una ruta que no ha iniciado."})
    ruta.paradas.all().delete()
    ruta.estado = Ruta.Estado.CANCELADA
    ruta.save(update_fields=["estado", "actualizado_en"])
    return ruta


def registrar_posicion(*, ruta, usuario, latitud, longitud, precision_metros, velocidad_kmh, rumbo):
    from config.coordenadas import validar_coordenadas

    if usuario.rol_nombre != Rol.Nombre.CONDUCTOR or ruta.conductor_id != usuario.id:
        raise PermissionDenied("Solo el conductor asignado envía la posición.")
    if ruta.estado != Ruta.Estado.EN_PROCESO:
        raise ValidationError({"detail": "La posición se envía cuando la ruta está en proceso."})
    latitud, longitud = validar_coordenadas(latitud, longitud)
    with transaction.atomic():
        posicion = Posicion.objects.create(
            ruta=ruta,
            latitud=latitud,
            longitud=longitud,
            precision_metros=precision_metros,
            velocidad_kmh=velocidad_kmh,
            rumbo=rumbo,
        )
        ruta.ultima_latitud = latitud
        ruta.ultima_longitud = longitud
        ruta.ultima_posicion_en = posicion.registrado_en
        ruta.save(update_fields=["ultima_latitud", "ultima_longitud", "ultima_posicion_en", "actualizado_en"])
    return posicion


def seguimiento_activo_para(usuario, ruta):
    if not ruta.dentro_de_lima or ruta.estado != Ruta.Estado.EN_PROCESO:
        return False
    if usuario.rol_nombre == Rol.Nombre.CLIENTE:
        return ruta.paradas.filter(destino__estado=Destino.Estado.EN_PROCESO).exists()
    return True


def puntos_de_mapa(usuario):
    qs = rutas_visibles(usuario).filter(estado=Ruta.Estado.EN_PROCESO, dentro_de_lima=True)
    if usuario.rol_nombre == Rol.Nombre.CLIENTE:
        qs = qs.filter(paradas__destino__estado=Destino.Estado.EN_PROCESO).distinct()
    return qs


def recalcular_rutas_de_punto(punto):
    rutas = Ruta.objects.filter(estado__in=ESTADOS_EDITABLES).filter(
        models_q(punto)
    )
    for ruta in rutas:
        recalcular_ruta(ruta)


def models_q(punto):
    return Q(base_origen=punto) | Q(base_final=punto)
