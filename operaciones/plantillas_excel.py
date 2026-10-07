from datetime import date
from io import BytesIO

from django.http import HttpResponse
from openpyxl import Workbook


def respuesta_excel(libro, nombre):
    buffer = BytesIO()
    libro.save(buffer)
    respuesta = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


def plantilla_destinos():
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Destinos"
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
    hoy = date.today().isoformat()
    hoja.append(
        [
            "G-001",
            hoy,
            "ENTREGA",
            "Pedido del cliente",
            "12345678",
            "Ana",
            "Diaz",
            "999999999",
            "Av. Ejemplo 123",
            "Miraflores",
            "Frente al parque",
            -12.1211,
            -77.0297,
            "",
            "",
        ]
    )
    hoja.append(
        [
            "T-001",
            hoy,
            "TRASLADO",
            "Traslado entre sedes",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "SEDE-01",
        ]
    )
    return respuesta_excel(libro, "plantilla_destinos.xlsx")


def plantilla_rutas():
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Rutas"
    hoja.append(
        [
            "codigo_ruta",
            "fecha",
            "ruc",
            "placa",
            "documento_conductor",
            "documentos_auxiliares",
            "codigo_base_origen",
            "codigo_base_final",
            "codigo_externo",
            "orden",
        ]
    )
    hoy = date.today().isoformat()
    hoja.append(["R-001", hoy, "20100000001", "ABC123", "87654321", "11223344", "BASE-PRINCIPAL", "BASE-PRINCIPAL", "G-001", 1])
    return respuesta_excel(libro, "plantilla_rutas.xlsx")
