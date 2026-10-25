"""Proteções contra SSRF e downloads abusivos para URLs informadas pelo usuário."""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

MAX_REDIRECTS = 5


class UnsafeURLError(ValueError):
    """URL inválida, não pública ou grande demais."""


def assert_public_url(url: str) -> None:
    """Rejeita URLs que não sejam http(s) ou que resolvam para IPs não públicos."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURLError("URL inválida. Deve começar com http:// ou https://")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except socket.gaierror:
        raise UnsafeURLError("Não foi possível resolver o endereço informado.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise UnsafeURLError("Endereço não permitido (rede local/privada).")


async def download_public_bytes(
    client: httpx.AsyncClient, url: str, max_bytes: int, headers: dict | None = None
) -> bytes:
    """Baixa o conteúdo seguindo redirects manualmente, validando cada destino e limitando o tamanho."""
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_url(url)
        async with client.stream("GET", url, headers=headers, follow_redirects=False) as resp:
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise UnsafeURLError("Redirecionamento inválido.")
                url = str(httpx.URL(url).join(location))
                continue
            if resp.status_code != 200:
                raise UnsafeURLError(f"Falha ao baixar imagem (HTTP {resp.status_code})")
            data = bytearray()
            async for chunk in resp.aiter_bytes():
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise UnsafeURLError("Arquivo excede o tamanho máximo permitido.")
            return bytes(data)
    raise UnsafeURLError("Redirecionamentos demais.")
