"""Exceção de regra de negócio com um código estável, usada pela sincronização offline (SDD 6.12)."""
from typing import Optional

from fastapi import HTTPException


class ErroRegra(HTTPException):
    """
    `HTTPException` que carrega um `codigo` de rejeição (ex.: FOTO_DEFEITO_AUSENTE). No endpoint online ela é uma
    resposta HTTP comum; na sincronização o `codigo` vira o `codigo` do resultado do evento.
    """

    def __init__(self, status_code: int, detail: str, codigo: Optional[str] = None):
        super().__init__(status_code=status_code, detail=detail)
        self.codigo = codigo
