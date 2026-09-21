# -*- coding: utf-8 -*-
"""IPv4 primero cuando el host tiene las dos familias, sin perder IPv6.

Medido el 2026-09-21 sobre `alagnapropiedades.com.ar`, el mismo sitio, la
misma pagina, los mismos **106.183 bytes** de respuesta:

    como esta hoy       5.444 ms
    forzando IPv4       1.462 ms
    como esta hoy       23.224 ms

No es variabilidad del sitio: es el handshake. Mirando las conexiones del
worker en vivo, una sola quedo **50 segundos en `SynSent`** contra una IPv6 de
Cloudflare antes de establecerse.

La IPv6 de esta maquina no esta muerta -a Google conecta en 20 ms- pero hacia
Cloudflare se cuelga: `cloudflare.com` por IPv6 dio 1.018 ms la primera vez y
timeout de mas de 12 s la segunda, contra 28 ms por IPv4.

Sondeados 400 hosts del padron:

    sin AAAA    317   79,2 %   no les afecta
    rapido       51   12,8 %
    lento        14    3,5 %   1 a 3 segundos de handshake
    colgado      18    4,5 %   mas de 6 segundos, timeout

O sea que el 8 % de los hosts paga entre segundos y un timeout entero **en cada
conexion**, y `alagnapropiedades.com.ar` -la agencia que consumio 2,3 h en tres
reinicios- es uno de los colgados. Ahi estaba el rendimiento, y no en las
muertes de worker que habia estado contando.

## Por que reordenar y no desactivar

Lo facil seria devolver solo IPv4. Seria peor: de los 83 hosts con AAAA, **51
conectan rapido por IPv6**, y hay redes donde IPv6 es el camino bueno o el
unico. `socket.create_connection` recorre la lista de `getaddrinfo` **en
orden** y se queda con la primera que conecta, asi que poner las IPv4 adelante
alcanza para no pagar el cuelgue, y las IPv6 siguen ahi como respaldo si la
IPv4 falla. No se pierde ninguna capacidad.

## Por que aca y no en el `Descargador`

`connectors/base.py` entra en la huella de certificacion: tocarlo invalida
certificaciones vigentes. Y no corresponde, porque esto **no cambia nada de lo
que se extrae** -los 106.183 bytes son identicos por las dos familias-. Es
politica de transporte del entorno donde corre la cola, no semantica del
conector, asi que vive en el runner, que no esta en la huella.

`database_writes: 0`.
"""
from __future__ import annotations

import socket

_ORIGINAL = None


def ipv4_primero(infos: list) -> list:
    """Las IPv4 adelante, las IPv6 detras, y dentro de cada familia el orden
    que vino. Nada se descarta."""
    v4 = [i for i in infos if i[0] == socket.AF_INET]
    otras = [i for i in infos if i[0] != socket.AF_INET]
    return v4 + otras


def preferir_ipv4() -> bool:
    """Instala el reordenamiento. Idempotente: llamarla dos veces no apila
    dos capas de patch, que es como se rompen estas cosas."""
    global _ORIGINAL
    if _ORIGINAL is not None:
        return False
    _ORIGINAL = socket.getaddrinfo

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return ipv4_primero(_ORIGINAL(host, port, family, type, proto, flags))

    socket.getaddrinfo = getaddrinfo
    return True


def restaurar() -> bool:
    """Para los tests y para cualquiera que quiera medir sin esto puesto."""
    global _ORIGINAL
    if _ORIGINAL is None:
        return False
    socket.getaddrinfo = _ORIGINAL
    _ORIGINAL = None
    return True
