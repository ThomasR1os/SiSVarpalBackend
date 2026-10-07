from rest_framework import serializers

from catalogos.models import Punto, Vehiculo
from config.coordenadas import CoordenadaField


class PuntoBreveSerializer(serializers.ModelSerializer):
    latitud = CoordenadaField()
    longitud = CoordenadaField()

    class Meta:
        model = Punto
        fields = ["id", "codigo", "nombre", "direccion", "distrito", "latitud", "longitud"]


class VehiculoBreveSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehiculo
        fields = ["id", "placa", "marca", "modelo", "tipo"]
