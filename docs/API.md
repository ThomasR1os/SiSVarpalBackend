# API SiSVarpal

Base: `http://localhost:8000`

Todas las rutas, salvo login y refresh, piden:

```http
Authorization: Bearer <access>
Content-Type: application/json
```

El access dura 15 minutos. El refresh dura 30 días. Solo hay una sesión por usuario: un login nuevo invalida el access y el refresh anteriores.

El inicio de sesión es con correo, no con usuario.

Latitud y longitud no tienen un largo fijo. Se guardan con los decimales que vengan, hasta 15. Una coordenada real de Google puede ser `"latitud": "-11.996963573604443"` y `"longitud": "-77.11872677728361"`. También vale `"-12.05"`. Si llegan más de 15 decimales, se recortan a 15. En el JSON viajan como texto para no perder dígitos. Envíalas como texto. La línea del mapa (`geometria.coordinates`) sigue siendo números `[longitud, latitud]`.

## Errores

```json
{
  "detail": "Error de validación",
  "errores": {
    "campo": ["Mensaje en español."]
  }
}
```

## Listados

Los listados responden paginados. `page` empieza en 1. `page_size` admite hasta 100. `search` busca en los campos de texto del recurso. `ordering` acepta los campos indicados en cada sección, con `-` para descendente.

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": []
}
```

## Roles

| Rol | Qué ve |
|---|---|
| ADMINISTRADOR | Todo. Arma clientes, destinos y rutas. |
| CONDUCTOR | Sus rutas confirmadas. Inicia, envía posición y cierra paradas. |
| AUXILIAR | Las rutas donde está asignado. Puede cerrar paradas y ver evidencias. No inicia la ruta. |
| CLIENTE | Destinos y rutas de su RUC, sin borradores. No ve la base final de Varpal ni el tramo de regreso. |

---

## Auth

### POST `/api/auth/login/`

```json
{
  "email": "admin@varpal.local",
  "password": "clave"
}
```

```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "user": {
    "id": 1,
    "email": "admin@varpal.local",
    "nombre": "Administrador",
    "apellido": "Varpal",
    "telefono": "",
    "documento": "00000000",
    "rol": "ADMINISTRADOR",
    "cliente_id": null,
    "is_active": true
  }
}
```

### POST `/api/auth/refresh/`

No envíes el access vencido. Solo el refresh.

```json
{ "refresh": "eyJ..." }
```

```json
{
  "access": "eyJ...",
  "refresh": "eyJ..."
}
```

El refresh anterior deja de servir. Si la sesión se abrió en otro dispositivo, la respuesta es 401:

```json
{
  "detail": "La sesión ya no es válida porque se inició sesión en otro lugar.",
  "errores": {}
}
```

### POST `/api/auth/logout/`

Sin cuerpo. Responde `204`. El access actual pasa a ser inválido.

### GET `/api/auth/me/`

Devuelve el mismo objeto `user` del login.

---

## Empresa

Solo administrador. Hay una sola empresa. El primer `PATCH` la crea y genera su punto principal, que es la base final por defecto.

### GET `/api/empresa/`

### PATCH `/api/empresa/`

```json
{
  "ruc": "20999999991",
  "razon_social": "Varpal",
  "telefono": "014445566",
  "email": "operaciones@varpal.pe",
  "direccion_principal": "Av. Empresa 100",
  "distrito": "Cercado de Lima",
  "latitud": "-12.046374",
  "longitud": "-77.042793"
}
```

```json
{
  "id": 1,
  "ruc": "20999999991",
  "razon_social": "Varpal",
  "telefono": "014445566",
  "email": "operaciones@varpal.pe",
  "direccion_principal": "Av. Empresa 100",
  "distrito": "Cercado de Lima",
  "latitud": "-12.046374",
  "longitud": "-77.042793"
}
```

El RUC tiene 11 dígitos. Latitud y longitud son obligatorias. Si faltan, no se guarda.

---

## Usuarios

Solo administrador. `DELETE` desactiva al usuario (`is_active: false`) y cierra su sesión. No borra la fila.

Filtros: `rol` (`ADMINISTRADOR`, `CONDUCTOR`, `AUXILIAR`, `CLIENTE`), `cliente`, `is_active`. Búsqueda: `email`, `nombre`, `apellido`, `documento`. El correo es obligatorio y único: con ese correo se inicia sesión.

### POST `/api/usuarios/`

El rol `CLIENTE` exige `cliente_id`. Los demás roles deben enviarlo en `null`.

```json
{
  "email": "conductor1@varpal.local",
  "password": "ClaveSegura123",
  "nombre": "Luis",
  "apellido": "Perez",
  "telefono": "999888777",
  "documento": "87654321",
  "rol": "CONDUCTOR",
  "cliente_id": null,
  "is_active": true
}
```

La respuesta omite `password` y repite el resto, con `id`.

### GET `/api/usuarios/` y GET `/api/usuarios/{id}/`

### PATCH `/api/usuarios/{id}/`

Envía solo los campos a cambiar. `password` es opcional.

### DELETE `/api/usuarios/{id}/`

`204`.

---

## Clientes

El administrador crea y edita. El usuario cliente solo consulta el suyo. `DELETE` lo marca inactivo.

Filtros: `activo`, `ruc`. Búsqueda: `ruc`, `razon_social`, `nombre_comercial`.

### POST `/api/clientes/`

Al guardar se crea o actualiza el punto principal (`codigo: "BASE-PRINCIPAL"`), que es la base de origen por defecto.

```json
{
  "ruc": "20111111111",
  "razon_social": "Cliente Demo",
  "nombre_comercial": "Demo",
  "telefono": "999111222",
  "email": "ops@demo.pe",
  "direccion_principal": "Av. Cliente 200",
  "distrito": "Miraflores",
  "latitud": "-12.09",
  "longitud": "-77.05",
  "activo": true
}
```

```json
{
  "id": 1,
  "ruc": "20111111111",
  "razon_social": "Cliente Demo",
  "nombre_comercial": "Demo",
  "telefono": "999111222",
  "email": "ops@demo.pe",
  "direccion_principal": "Av. Cliente 200",
  "distrito": "Miraflores",
  "latitud": "-12.09",
  "longitud": "-77.05",
  "activo": true
}
```

### GET `/api/clientes/` y GET `/api/clientes/{id}/`

### PATCH `/api/clientes/{id}/`

### DELETE `/api/clientes/{id}/`

`204`.

---

## Puntos

Bases de origen, sedes y la base final de Varpal. La dirección principal no se edita aquí: se actualiza en el cliente o en la empresa.

Filtros: `cliente`, `es_sede`, `es_base_origen`, `es_base_final`, `es_principal`, `activo`, `de_varpal` (`true` o `false`).

### POST `/api/puntos/`

Sede de un cliente:

```json
{
  "cliente_id": 1,
  "codigo": "SEDE-01",
  "nombre": "Sede Norte",
  "direccion": "Av. Las Flores 50",
  "distrito": "Los Olivos",
  "latitud": "-11.959",
  "longitud": "-77.070",
  "es_base_origen": false,
  "es_sede": true,
  "es_base_final": false,
  "activo": true
}
```

Base final adicional de Varpal, sin cliente:

```json
{
  "cliente_id": null,
  "codigo": "BASE-CALLAO",
  "nombre": "Base Callao",
  "direccion": "Av. Argentina 1200",
  "distrito": "Callao",
  "latitud": "-12.046",
  "longitud": "-77.135",
  "es_base_origen": false,
  "es_sede": false,
  "es_base_final": true,
  "activo": true
}
```

```json
{
  "id": 3,
  "cliente_id": 1,
  "codigo": "SEDE-01",
  "nombre": "Sede Norte",
  "direccion": "Av. Las Flores 50",
  "distrito": "Los Olivos",
  "latitud": "-11.959",
  "longitud": "-77.07",
  "es_principal": false,
  "es_base_origen": false,
  "es_sede": true,
  "es_base_final": false,
  "activo": true
}
```

### GET, PATCH `/api/puntos/{id}/`

### DELETE `/api/puntos/{id}/`

`204` si no está en uso. La principal no se elimina.

---

## Vehículos

Flota de la empresa. `DELETE` desactiva. El cliente no lista vehículos.

### POST `/api/vehiculos/`

```json
{
  "placa": "ABC123",
  "marca": "Hyundai",
  "modelo": "H100",
  "tipo": "Furgón",
  "capacidad_kg": 1500,
  "activo": true
}
```

La placa se guarda en mayúsculas y sin espacios.

```json
{
  "id": 1,
  "placa": "ABC123",
  "marca": "Hyundai",
  "modelo": "H100",
  "tipo": "Furgón",
  "capacidad_kg": 1500.0,
  "activo": true
}
```

---

## Motivos

Catálogo de por qué no se cumplió el destino. No es el motivo del servicio. `DELETE` desactiva. Conductor y auxiliar solo ven los activos.

`aplica_a`: `NO_LLEGO`, `SERVICIO_FALLIDO`, `AMBOS`.

### POST `/api/motivos/`

```json
{
  "codigo": "AUSENTE",
  "descripcion": "No había nadie en el destino",
  "aplica_a": "AMBOS",
  "activo": true
}
```

```json
{
  "id": 1,
  "codigo": "AUSENTE",
  "descripcion": "No había nadie en el destino",
  "aplica_a": "AMBOS",
  "activo": true
}
```

El comando inicial ya carga: `AUSENTE`, `DIRECCION`, `CERRADO`, `RECHAZO`, `DANADA`.

---

## Plantillas de Excel

Solo administrador. Traducen los encabezados del archivo del cliente a los campos internos. Si no hay plantilla activa, el Excel debe usar los nombres canónicos.

### POST `/api/plantillas/`

```json
{
  "cliente_id": 1,
  "tipo": "DESTINOS",
  "nombre": "Formato Demo",
  "activa": true,
  "mapeo_columnas": {
    "Guia": "codigo_externo",
    "Fecha": "fecha",
    "Servicio": "tipo_servicio",
    "Motivo": "motivo_servicio",
    "DNI": "documento_receptor",
    "Nombres": "nombre_receptor",
    "Apellidos": "apellido_receptor",
    "Celular": "telefono_receptor",
    "Direccion": "direccion",
    "Distrito": "distrito",
    "Lat": "latitud",
    "Lng": "longitud"
  }
}
```

`tipo`: `DESTINOS` o `RUTAS`. Solo una plantilla activa por cliente y tipo. Las columnas del Excel que no están en el mapeo se guardan en `datos_extra` del destino.

---

## Geocerca

Solo administrador. El mapa en vivo usa la geocerca activa. El comando inicial crea "Lima metropolitana".

### GET `/api/geocerca/`

```json
{
  "id": 1,
  "nombre": "Lima metropolitana",
  "poligono": [
    [-77.23, -11.72],
    [-76.68, -11.72],
    [-76.68, -12.52],
    [-77.23, -12.52],
    [-77.23, -11.72]
  ],
  "activa": true
}
```

Cada punto es `[longitud, latitud]`.

### PUT `/api/geocerca/`

Reemplaza el polígono activo. Mismo cuerpo, sin `id` ni `activa`.

---

## Destinos

Un destino es una parada. Estados: `NO_INICIADO`, `EN_PROCESO`, `EXITOSO`, `FALLIDO`.

Tipos: `ENTREGA`, `INTERCAMBIO`, `RECOJO`, `TRASLADO`.

Filtros: `cliente`, `fecha` (`AAAA-MM-DD`), `estado`, `tipo_servicio`, `sin_ruta` (`true` para los que aún no están en una ruta).

El administrador crea, edita, reprograma, importa y elimina. Solo se edita o elimina si está `NO_INICIADO` y, para eliminar, si no está en una ruta. Reprogramar a otra fecha lo saca de la ruta si esa ruta todavía no inició. La fecha no puede ser anterior a hoy.

En un traslado, `sede_id` es obligatorio y la dirección y las coordenadas salen de la sede. En los otros tipos, dirección, distrito, receptor y coordenadas son obligatorios.

### POST `/api/destinos/`

```json
{
  "cliente_id": 1,
  "fecha": "2026-10-07",
  "codigo_externo": "G-001",
  "tipo_servicio": "ENTREGA",
  "sede_id": null,
  "documento_receptor": "12345678",
  "nombre_receptor": "Ana",
  "apellido_receptor": "Diaz",
  "telefono_receptor": "999999999",
  "direccion": "Calle Destino 10",
  "distrito": "Miraflores",
  "referencia": "Frente al parque",
  "latitud": "-12.1",
  "longitud": "-77.04",
  "motivo_servicio": "Pedido del cliente",
  "observaciones": "",
  "datos_extra": {}
}
```

```json
{
  "id": 10,
  "cliente_id": 1,
  "fecha": "2026-10-07",
  "codigo_externo": "G-001",
  "tipo_servicio": "ENTREGA",
  "sede_id": null,
  "documento_receptor": "12345678",
  "nombre_receptor": "Ana",
  "apellido_receptor": "Diaz",
  "telefono_receptor": "999999999",
  "direccion": "Calle Destino 10",
  "distrito": "Miraflores",
  "referencia": "Frente al parque",
  "latitud": "-12.1",
  "longitud": "-77.04",
  "motivo_servicio": "Pedido del cliente",
  "observaciones": "",
  "datos_extra": {},
  "estado": "NO_INICIADO",
  "motivo_id": null,
  "observacion_cierre": "",
  "ruta_id": null,
  "creado_en": "2026-10-07T15:00:00.000000Z",
  "actualizado_en": "2026-10-07T15:00:00.000000Z"
}
```

### GET `/api/destinos/` y GET `/api/destinos/{id}/`

### PATCH `/api/destinos/{id}/`

### DELETE `/api/destinos/{id}/`

`204`.

### POST `/api/destinos/{id}/reprogramar/`

```json
{ "fecha": "2026-10-08" }
```

Devuelve el destino actualizado.

### POST `/api/destinos/{id}/cerrar/`

`multipart/form-data`. Lo hace el conductor o un auxiliar de esa ruta, o un administrador. El destino debe estar `EN_PROCESO`. Mínimo 1 foto y máximo 10. JPG, PNG o WEBP.

| Campo | Regla |
|---|---|
| resultado | `EXITOSO` o `FALLIDO` |
| motivo_id | Obligatorio si es `FALLIDO`. Se ignora si es `EXITOSO`. |
| observacion | Texto opcional |
| fotos | Uno o más archivos. El servidor los sube a Cloudinary. |

```json
{
  "id": 10,
  "estado": "FALLIDO",
  "motivo_id": 1,
  "observacion_cierre": "Timbré y no abrieron",
  "ruta_id": 4
}
```

El resto de campos del destino viaja igual.

### GET `/api/destinos/{id}/evidencias/`

```json
[
  {
    "id": 1,
    "archivo": "https://res.cloudinary.com/zwpuvmw7/image/upload/varpal/evidencias/10/foto.png",
    "creado_en": "2026-10-07T18:40:00.000000Z"
  }
]
```

### GET `/api/destinos/plantilla/`

Descarga `plantilla_destinos.xlsx`. Columnas:

`codigo_externo`, `fecha`, `tipo_servicio`, `motivo_servicio`, `documento_receptor`, `nombre_receptor`, `apellido_receptor`, `telefono_receptor`, `direccion`, `distrito`, `referencia`, `latitud`, `longitud`, `observaciones`, `codigo_sede`.

En `TRASLADO`, `codigo_sede` es obligatorio y las coordenadas salen de la sede. En los demás tipos, latitud y longitud son obligatorias. Una fila sin coordenadas se rechaza y no se crea.

### POST `/api/destinos/importar/`

`multipart/form-data`: `cliente_id`, `archivo`.

```json
{
  "creados": 1,
  "destinos": [11],
  "rechazados": [
    {
      "fila": 3,
      "errores": ["latitud: La latitud es obligatoria."]
    }
  ]
}
```

`fila` es el número de fila del Excel, contando el encabezado como 1.

---

## Rutas

Estados: `BORRADOR`, `NO_INICIADA`, `EN_PROCESO`, `FINALIZADA`, `CANCELADA`.

El conductor, el auxiliar y el cliente no ven borradores. Una ruta solo agrupa destinos del mismo cliente y de la misma fecha, de hoy en adelante. Un destino solo puede estar en una ruta. Un conductor puede tener varias rutas el mismo día, pero solo una `EN_PROCESO`.

Si no envías `base_origen_id`, se usa la dirección principal del cliente. Si no envías `base_final_id`, se usa la de Varpal. La base final no es una parada: el cliente no la recibe.

Filtros: `cliente`, `fecha`, `estado`, `conductor`, `vehiculo`.

### POST `/api/rutas/`

Crea la ruta en `BORRADOR`. `optimizar: true` ordena las paradas por cercanía desde la base del cliente. La base de Varpal queda fija al final del cálculo de la empresa.

```json
{
  "cliente_id": 1,
  "fecha": "2026-10-07",
  "conductor_id": 2,
  "vehiculo_id": 1,
  "auxiliar_ids": [3],
  "base_origen_id": null,
  "base_final_id": null,
  "destino_ids": [10, 11],
  "optimizar": true
}
```

Hasta 4 auxiliares.

```json
{
  "id": 4,
  "cliente_id": 1,
  "cliente_nombre": "Cliente Demo",
  "fecha": "2026-10-07",
  "estado": "BORRADOR",
  "conductor": {
    "id": 2,
    "email": "conductor1@varpal.local",
    "nombre": "Luis",
    "apellido": "Perez",
    "documento": "87654321",
    "rol": "CONDUCTOR"
  },
  "vehiculo": {
    "id": 1,
    "placa": "ABC123",
    "marca": "Hyundai",
    "modelo": "H100",
    "tipo": "Furgón"
  },
  "auxiliares": [],
  "base_origen": {
    "id": 2,
    "codigo": "BASE-PRINCIPAL",
    "nombre": "Cliente Demo",
    "direccion": "Av. Cliente 200",
    "distrito": "Miraflores",
    "latitud": "-12.09",
    "longitud": "-77.05"
  },
  "base_final": {
    "id": 1,
    "codigo": "BASE-PRINCIPAL",
    "nombre": "Varpal",
    "direccion": "Av. Empresa 100",
    "distrito": "Cercado de Lima",
    "latitud": "-12.046374",
    "longitud": "-77.042793"
  },
  "paradas": [
    {
      "id": 8,
      "orden": 1,
      "destino_id": 10,
      "codigo_externo": "G-001",
      "tipo_servicio": "ENTREGA",
      "estado": "NO_INICIADO",
      "direccion": "Calle Destino 10",
      "distrito": "Miraflores",
      "latitud": "-12.1",
      "longitud": "-77.04",
      "nombre_receptor": "Ana",
      "apellido_receptor": "Diaz",
      "hora_estimada": null,
      "hora_llegada": null,
      "hora_salida": null
    }
  ],
  "distancia_metros": 18400,
  "duracion_segundos": 2650,
  "geometria_cliente": {
    "type": "LineString",
    "coordinates": [[-77.05, -12.09], [-77.04, -12.1]]
  },
  "geometria_empresa": {
    "type": "LineString",
    "coordinates": [[-77.05, -12.09], [-77.04, -12.1], [-77.042793, -12.046374]]
  },
  "dentro_de_lima": true,
  "iniciada_en": null,
  "llegada_base_en": null,
  "finalizada_en": null,
  "ultima_latitud": null,
  "ultima_longitud": null,
  "ultima_posicion_en": null
}
```

Para el rol `CLIENTE` la misma ruta no incluye `base_final` ni `geometria_empresa`. `distancia_metros` y `duracion_segundos` cubren solo de la base del cliente a la última parada. En la respuesta de empresa suman el regreso a la base de Varpal.

Las coordenadas de la línea son `[longitud, latitud]`. El `LineString` sigue las calles: trae los puntos intermedios del callejero, no solo el origen, las paradas y la base. La distancia y la duración salen de ese mismo recorrido en auto. El ejemplo de arriba está abreviado.

Si el motor de rutas no responde, la ruta se guarda igual y la línea queda en recta. En ese respaldo la duración se estima a 25 km/h. Cuando el motor responde, lo que queda guardado es el trazado por calles.

`optimizar: true` y `POST /api/rutas/optimizar/` ordenan las paradas por la distancia por calle desde la base del cliente. La base de Varpal sigue fija al final y no entra en ese orden.

### GET `/api/rutas/` y GET `/api/rutas/{id}/`

### PATCH `/api/rutas/{id}/`

Mientras esté en `BORRADOR` o `NO_INICIADA`. Mismos campos del alta, todos opcionales. Si cambias la fecha, los destinos ya deben tener esa fecha.

### POST `/api/rutas/optimizar/`

No guarda nada. Sirve para previsualizar el orden.

```json
{
  "cliente_id": 1,
  "fecha": "2026-10-07",
  "base_origen_id": null,
  "base_final_id": null,
  "destino_ids": [11, 10]
}
```

```json
{
  "destino_ids": [10, 11],
  "paradas": [
    {
      "orden": 1,
      "destino_id": 10,
      "codigo_externo": "G-001",
      "direccion": "Calle Destino 10",
      "distrito": "Miraflores",
      "latitud": "-12.1",
      "longitud": "-77.04"
    }
  ],
  "distancia_metros": 18400,
  "duracion_segundos": 2650,
  "geometria_empresa": { "type": "LineString", "coordinates": [] },
  "geometria_cliente": { "type": "LineString", "coordinates": [] },
  "dentro_de_lima": true
}
```

### PATCH `/api/rutas/{id}/orden/`

```json
{ "destino_ids": [11, 10] }
```

Debe incluir exactamente las paradas de la ruta, sin repetir. Devuelve la ruta.

### POST `/api/rutas/{id}/confirmar/`

Pasa de `BORRADOR` a `NO_INICIADA`. Ahí la ve el conductor. Sin cuerpo.

### POST `/api/rutas/{id}/iniciar/`

Solo el conductor asignado. Sin cuerpo. La ruta y sus destinos pasan a `EN_PROCESO`. Cada administrador recibe una notificación. Si ya tiene otra ruta en proceso, responde 400.

### POST `/api/rutas/{id}/llegada-base/`

Conductor o administrador. Sin cuerpo. Exige que todas las paradas estén `EXITOSO` o `FALLIDO`. La ruta pasa a `FINALIZADA`.

### POST `/api/rutas/{id}/cancelar/`

Solo si no ha iniciado. Suelta los destinos para poder asignarlos a otra ruta. Pasa a `CANCELADA`.

### POST `/api/rutas/{id}/posiciones/`

Solo el conductor, con la ruta `EN_PROCESO`. La app debe enviarla cada 10 o 15 segundos.

```json
{
  "latitud": "-12.095",
  "longitud": "-77.045",
  "precision_metros": 8,
  "velocidad_kmh": 22,
  "rumbo": 90
}
```

`precision_metros`, `velocidad_kmh` y `rumbo` son opcionales.

```json
{
  "id": 50,
  "latitud": "-12.095",
  "longitud": "-77.045",
  "precision_metros": 8.0,
  "velocidad_kmh": 22.0,
  "rumbo": 90.0,
  "registrado_en": "2026-10-07T18:10:00.000000Z"
}
```

### GET `/api/rutas/{id}/seguimiento/`

Orden de paradas y, si corresponde, el camión.

```json
{
  "ruta_id": 4,
  "cliente_id": 1,
  "estado": "EN_PROCESO",
  "fecha": "2026-10-07",
  "dentro_de_lima": true,
  "en_vivo": true,
  "seguimiento_activo": true,
  "base_origen": {
    "id": 2,
    "codigo": "BASE-PRINCIPAL",
    "nombre": "Cliente Demo",
    "direccion": "Av. Cliente 200",
    "distrito": "Miraflores",
    "latitud": "-12.09",
    "longitud": "-77.05"
  },
  "base_final": {
    "id": 1,
    "codigo": "BASE-PRINCIPAL",
    "nombre": "Varpal",
    "direccion": "Av. Empresa 100",
    "distrito": "Cercado de Lima",
    "latitud": "-12.046374",
    "longitud": "-77.042793"
  },
  "geometria": {
    "type": "LineString",
    "coordinates": [[-77.05, -12.09], [-77.04, -12.1], [-77.042793, -12.046374]]
  },
  "paradas": [
    {
      "orden": 1,
      "destino_id": 10,
      "codigo_externo": "G-001",
      "estado": "EN_PROCESO",
      "direccion": "Calle Destino 10",
      "distrito": "Miraflores",
      "latitud": "-12.1",
      "longitud": "-77.04",
      "nombre_receptor": "Ana"
    }
  ],
  "ultima_posicion": {
    "latitud": "-12.095",
    "longitud": "-77.045",
    "registrado_en": "2026-10-07T18:10:00.000000Z"
  },
  "recorrido": [
    {
      "latitud": "-12.095",
      "longitud": "-77.045",
      "registrado_en": "2026-10-07T18:10:00.000000Z"
    }
  ]
}
```

Reglas del seguimiento:

- El cliente no recibe `base_final`. Su `geometria` termina en la última parada.
- Administrador, conductor y auxiliar reciben la geometría hasta la base de Varpal.
- `en_vivo` es true solo si la ruta está `EN_PROCESO`, todos sus puntos caen en la geocerca y, para el cliente, todavía queda una parada `EN_PROCESO`.
- Si `en_vivo` es false, `ultima_posicion` es `null` y `recorrido` es `[]`.
- El recorrido devuelve como máximo los últimos 500 puntos, del más antiguo al más nuevo.

### GET `/api/rutas/plantilla/`

Descarga `plantilla_rutas.xlsx`. Una fila por parada. Columnas:

`codigo_ruta`, `fecha`, `ruc`, `placa`, `documento_conductor`, `documentos_auxiliares`, `codigo_base_origen`, `codigo_base_final`, `codigo_externo`, `orden`.

`documentos_auxiliares` va separado por comas. `codigo_base_origen` y `codigo_base_final` pueden ir vacíos para usar las direcciones principales. El archivo crea rutas en borrador.

### POST `/api/rutas/importar/`

`multipart/form-data` con `archivo`.

```json
{
  "creados": 1,
  "rutas": [5],
  "rechazados": [
    {
      "fila": 4,
      "errores": ["codigo_externo: Fila 4: no existe el destino G-999 en esa fecha."]
    }
  ]
}
```

---

## Mapa en vivo

### GET `/api/mapa/rutas/`

No está paginado. Solo rutas `EN_PROCESO` dentro de Lima. El cliente solo ve las suyas que todavía tienen una parada en proceso. Cada elemento tiene la misma forma que el seguimiento.

```json
{
  "results": []
}
```

El frontend puede consultar este endpoint, o el seguimiento de una ruta, cada 10 segundos.

---

## Notificaciones

Cada administrador recibe una cuando un conductor inicia una ruta. Cada usuario solo ve las suyas.

### GET `/api/notificaciones/`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "ruta_id": 4,
      "tipo": "RUTA_INICIADA",
      "titulo": "Ruta iniciada",
      "cuerpo": "Luis Perez inició la ruta 4 del 07/10/2026.",
      "leida": false,
      "creado_en": "2026-10-07T18:00:00.000000Z"
    }
  ]
}
```

### POST `/api/notificaciones/{id}/leer/`

Devuelve la notificación con `leida: true`.

### POST `/api/notificaciones/leer-todas/`

```json
{ "actualizadas": 2 }
```

---

## Orden para armar una operación

1. `PATCH /api/empresa/` con la dirección principal de Varpal.
2. Crear el cliente. Eso deja su base de origen.
3. Crear sedes, vehículos, conductores y auxiliares.
4. Cargar destinos, a mano o con el Excel.
5. `POST /api/rutas/optimizar/` para ver el orden, o `POST /api/rutas/` con `optimizar: true`.
6. `POST /api/rutas/{id}/confirmar/`.
7. El conductor llama `POST /api/rutas/{id}/iniciar/` y empieza a enviar posiciones.
8. Cierra cada parada con foto.
9. `POST /api/rutas/{id}/llegada-base/` al llegar a Varpal.

Para levantar el API en local, con el entorno virtual activo:

```bash
python manage.py migrate
python manage.py datos_iniciales
python manage.py runserver
```

El trazado por calles usa un OSRM propio con el perfil de auto, sobre OpenStreetMap de Lima metropolitana. No se usa el servidor público de demostración. `OSRM_BASE_URL` apunta a ese servicio (en local, `http://127.0.0.1:5000`).

La primera vez, con Docker en marcha:

```powershell
infra\osrm\preparar.ps1
docker compose -f infra\osrm\docker-compose.yml up -d
```

El administrador inicial entra con el correo `admin@varpal.local`. La clave es la variable `ADMIN_PASSWORD` del archivo `.env`.
