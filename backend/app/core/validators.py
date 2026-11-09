"""Validadores compartilhados (SDD seção 7, PR-34)."""
import re


def normalizar_cpf(valor: str) -> str:
    """Remove qualquer caractere não numérico."""
    return re.sub(r"\D", "", valor or "")


def cpf_valido(valor: str) -> bool:
    """CPF válido: 11 dígitos, não repetidos, dígitos verificadores corretos."""
    cpf = normalizar_cpf(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def validar_cpf(valor: str) -> str:
    """Retorna o CPF só com dígitos ou levanta ValueError("CPF inválido")."""
    if not cpf_valido(valor):
        raise ValueError("CPF inválido")
    return normalizar_cpf(valor)
