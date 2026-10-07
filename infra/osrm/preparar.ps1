$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$datos = Join-Path $raiz "data"
New-Item -ItemType Directory -Force -Path $datos | Out-Null

$peru = Join-Path $datos "peru-latest.osm.pbf"
if (-not (Test-Path $peru)) {
    Write-Host "Descargando OpenStreetMap de Peru..."
    curl.exe -L --fail --retry 3 -o $peru "https://download.geofabrik.de/south-america/peru-latest.osm.pbf"
}

$metro = Join-Path $datos "lima-metro.osm.pbf"
if (-not (Test-Path $metro)) {
    Write-Host "Recortando Lima metropolitana..."
    docker run --rm -v "${datos}:/data" stefda/osmium-tool osmium extract -b -77.35,-12.62,-76.58,-11.62 --strategy complete_ways -o /data/lima-metro.osm.pbf /data/peru-latest.osm.pbf
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$imagen = "ghcr.io/project-osrm/osrm-backend:v5.27.1"
if (-not (Test-Path (Join-Path $datos "lima-metro.osrm.mldgr"))) {
    Write-Host "Preparando el grafo de auto..."
    docker run --rm -v "${datos}:/data" $imagen osrm-extract -p /opt/car.lua /data/lima-metro.osm.pbf
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    docker run --rm -v "${datos}:/data" $imagen osrm-partition /data/lima-metro.osrm
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    docker run --rm -v "${datos}:/data" $imagen osrm-customize /data/lima-metro.osrm
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Listo. Levanta el motor con: docker compose -f infra/osrm/docker-compose.yml up -d"
