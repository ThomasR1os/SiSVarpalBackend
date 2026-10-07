from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

COORD_MAX_DIGITS = 18
COORD_DECIMAL_PLACES = 15
CUANTUM = Decimal("0.000000000000001")


def a_decimal_coordenada(valor):
    if isinstance(valor, Decimal):
        texto = format(valor, "f")
    else:
        texto = str(valor).strip().replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError("coordenada inválida") from exc
    return numero.quantize(CUANTUM, rounding=ROUND_HALF_UP)


def coordenada_texto(valor):
    if valor is None or valor == "":
        return None
    texto = format(a_decimal_coordenada(valor), "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto


class CoordenadaField(serializers.Field):
    def to_internal_value(self, data):
        if data is None or data == "":
            if self.allow_null:
                return None
            self.fail("required")
        try:
            return a_decimal_coordenada(data)
        except ValueError as exc:
            raise serializers.ValidationError("Debe ser una coordenada numérica.") from exc

    def to_representation(self, value):
        return coordenada_texto(value)


def validar_coordenadas(latitud, longitud, campo_lat="latitud", campo_lng="longitud"):
    errores = {}
    if latitud is None or latitud == "":
        errores[campo_lat] = ["La latitud es obligatoria."]
    else:
        try:
            latitud = a_decimal_coordenada(latitud)
        except ValueError:
            errores[campo_lat] = ["La latitud debe ser numérica."]
        else:
            if not Decimal("-90") <= latitud <= Decimal("90"):
                errores[campo_lat] = ["La latitud debe estar entre -90 y 90."]
    if longitud is None or longitud == "":
        errores[campo_lng] = ["La longitud es obligatoria."]
    else:
        try:
            longitud = a_decimal_coordenada(longitud)
        except ValueError:
            errores[campo_lng] = ["La longitud debe ser numérica."]
        else:
            if not Decimal("-180") <= longitud <= Decimal("180"):
                errores[campo_lng] = ["La longitud debe estar entre -180 y 180."]
    if errores:
        raise ValidationError(errores)
    return latitud, longitud
