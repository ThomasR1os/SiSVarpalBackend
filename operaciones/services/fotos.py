import logging
import os
from urllib.parse import unquote, urlparse

import cloudinary
import cloudinary.uploader
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _configurar():
    crudo = os.environ.get("CLOUDINARY_URL", "")
    partes = urlparse(crudo)
    if partes.scheme != "cloudinary" or not partes.hostname or not partes.username or not partes.password:
        raise ValidationError({"fotos": ["Cloudinary no está configurado."]})
    cloudinary.config(
        cloud_name=partes.hostname,
        api_key=unquote(partes.username),
        api_secret=unquote(partes.password),
        secure=True,
    )


def subir_foto(archivo, destino_id):
    _configurar()
    archivo.seek(0)
    try:
        resultado = cloudinary.uploader.upload(
            archivo,
            folder=f"varpal/evidencias/{destino_id}",
            resource_type="image",
        )
    except Exception:
        logger.exception("No se pudo subir la evidencia del destino %s", destino_id)
        raise ValidationError({"fotos": ["No se pudo subir la foto."]}) from None
    url = resultado.get("secure_url")
    if not url:
        raise ValidationError({"fotos": ["No se pudo subir la foto."]})
    return url
