"""
Cliente do Supabase Storage (bucket PRIVADO) para fotos, comprovantes e assinaturas cifradas (SEG-09 / PR-03).

Fala com a API REST do Storage por `httpx` (já é dependência do projeto). Quem chama é sempre o BACKEND, com a chave de
serviço (`SUPABASE_SERVICE_KEY`), que ignora o RLS: a permissão do usuário sobre a OS é checada ANTES, na API. Nenhuma
política é criada em `storage.objects` (acesso de anon/authenticated negado) e o bucket não é público: a única forma de
ler um objeto é por esta chave (ou por link assinado, que este módulo ainda não emite).

Interface (a mesma do armazenamento em disco de `file_service`): put / get / delete, por `area` ("uploads" |
"assinaturas") e `nome`. O objeto fica em `<area>/<nome>` dentro do bucket. A coluna `url` do banco continua guardando a
referência lógica `/static/uploads/<nome>` (não muda), o que mantém válidos os selos de integridade já gravados.

STATUS: a montagem das requisições é coberta por testes com transporte simulado; o comportamento contra o servidor REAL
do Supabase só é conferido ao rodar `scripts/testar_storage.py` com as credenciais.
"""
import logging
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

AREAS = ("uploads", "assinaturas")


class SupabaseStorage:
    def __init__(self, url: str, chave: str, bucket: str, *, client: Optional[httpx.Client] = None,
                 timeout: float = 60.0) -> None:
        self._base = f"{url.rstrip('/')}/storage/v1"
        self._bucket = bucket
        self._chave = chave
        self._client = client or httpx.Client(timeout=timeout)

    # -- helpers ---------------------------------------------------------------------------------------------------
    def _headers(self, extra: Optional[dict] = None) -> dict:
        # Chaves NOVAS (`sb_secret_...`) não são JWT: vão SÓ em `apikey`; no `Authorization: Bearer` a plataforma tenta
        # lê-las como JWT e rejeita ("Invalid Compact JWS"). A chave ANTIGA `service_role` (JWT) segue nos dois cabeçalhos.
        h = {"apikey": self._chave}
        if not self._chave.startswith("sb_"):
            h["Authorization"] = f"Bearer {self._chave}"
        if extra:
            h.update(extra)
        return h

    def _caminho(self, area: str, nome: str) -> str:
        if area not in AREAS or not nome or "/" in nome or nome in (".", ".."):
            raise ValueError(f"Referência de arquivo inválida: {area!r}/{nome!r}")
        return f"{quote(self._bucket, safe='')}/{quote(area, safe='')}/{quote(nome, safe='')}"

    @staticmethod
    def _indisponivel(operacao: str, exc: Optional[Exception] = None, resposta: Optional[httpx.Response] = None):
        # Nunca registra a chave nem o corpo enviado; o corpo da resposta de erro do Storage não contém segredos.
        detalhe = f"HTTP {resposta.status_code} {resposta.text[:200]}" if resposta is not None else repr(exc)
        logger.error("Supabase Storage: falha em %s (%s)", operacao, detalhe)
        return HTTPException(status_code=503, detail="Armazenamento de arquivos indisponível. Tente novamente.")

    @staticmethod
    def _nao_encontrado(resposta: httpx.Response) -> bool:
        """O Storage responde 404 ou 400 com `statusCode 404` / `not_found` no corpo para objeto inexistente."""
        if resposta.status_code == 404:
            return True
        if resposta.status_code == 400:
            corpo = resposta.text.lower()
            return "not_found" in corpo or "not found" in corpo or '"404"' in corpo
        return False

    # -- interface -------------------------------------------------------------------------------------------------
    def put(self, area: str, nome: str, dados: bytes, content_type: str) -> None:
        """Grava o objeto SEM sobrescrever (`x-upsert: false`): nome repetido é erro, nunca troca silenciosa."""
        try:
            r = self._client.post(f"{self._base}/object/{self._caminho(area, nome)}", content=dados,
                                  headers=self._headers({"Content-Type": content_type, "x-upsert": "false",
                                                         "Cache-Control": "max-age=300"}))
        except httpx.HTTPError as exc:
            raise self._indisponivel("upload", exc=exc)
        if r.status_code not in (200, 201):
            raise self._indisponivel("upload", resposta=r)

    def get(self, area: str, nome: str) -> Optional[bytes]:
        """Bytes do objeto, ou None se não existir. Endpoint autenticado (bucket privado)."""
        try:
            r = self._client.get(f"{self._base}/object/authenticated/{self._caminho(area, nome)}",
                                 headers=self._headers())
        except httpx.HTTPError as exc:
            raise self._indisponivel("download", exc=exc)
        if r.status_code == 200:
            return r.content
        if self._nao_encontrado(r):
            return None
        raise self._indisponivel("download", resposta=r)

    def delete(self, area: str, nome: str) -> None:
        """Remove o objeto; inexistente não é erro (idempotente)."""
        try:
            r = self._client.delete(f"{self._base}/object/{self._caminho(area, nome)}", headers=self._headers())
        except httpx.HTTPError as exc:
            raise self._indisponivel("remoção", exc=exc)
        if r.status_code in (200, 204) or self._nao_encontrado(r):
            return
        raise self._indisponivel("remoção", resposta=r)
