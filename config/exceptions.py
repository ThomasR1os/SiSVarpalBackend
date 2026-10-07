from rest_framework.views import exception_handler


def _como_lista(valor):
    if isinstance(valor, list):
        return [str(item) for item in valor]
    if isinstance(valor, dict):
        return [str(valor)]
    return [str(valor)]


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, list):
        response.data = {"detail": "Error de validación", "errores": {"non_field_errors": _como_lista(data)}}
        return response
    if not isinstance(data, dict):
        response.data = {"detail": str(data), "errores": {}}
        return response

    detail = data.get("detail")
    errores = {}
    for clave, valor in data.items():
        if clave == "detail":
            continue
        if isinstance(valor, dict):
            errores[clave] = {sub: _como_lista(subvalor) for sub, subvalor in valor.items()}
        else:
            errores[clave] = _como_lista(valor)

    if detail is None:
        detail = "Error de validación" if errores else "Error"
    elif isinstance(detail, list):
        detail = str(detail[0]) if detail else "Error"
    else:
        detail = str(detail)

    response.data = {"detail": detail, "errores": errores}
    return response
