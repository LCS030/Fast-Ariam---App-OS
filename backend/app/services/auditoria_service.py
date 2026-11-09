"""
Auditoria (PR-20 / SEG-06): registra ações relevantes da OS em `log_acao` e no logger da aplicação.

O registro entra na MESMA transação da ação (apenas `session.add`); quem chama confirma com commit. Assim a trilha
nunca fica adiantada nem atrasada em relação ao dado. NÃO registrar tokens, senhas, CPF completo, dados bancários nem
conteúdo binário no `payload`.
"""
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("fast_ariam.auditoria")

# Nomes de ação (log_acao.acao, VARCHAR(50)).
OS_CRIADA = "OS_CRIADA"
OS_ATRIBUIDA = "OS_ATRIBUIDA"
OS_ATUALIZADA = "OS_ATUALIZADA"
OS_CANCELADA = "OS_CANCELADA"
OS_PAUSADA = "OS_PAUSADA"
OS_REAGENDADA = "OS_REAGENDADA"
OS_AGUARDANDO_REAGENDAMENTO = "OS_AGUARDANDO_REAGENDAMENTO"
OS_FINALIZADA = "OS_FINALIZADA"
ATENDIMENTO_INICIADO = "ATENDIMENTO_INICIADO"
ATENDIMENTO_FINALIZADO = "ATENDIMENTO_FINALIZADO"
UPLOAD_ARQUIVO = "UPLOAD_ARQUIVO"
DESATRIBUIDA_POR_DESATIVACAO = "DESATRIBUIDA_POR_DESATIVACAO"
# v0.5 - equipamentos da OS (SDD 6.13)
EQUIPAMENTO_MODELO_CRIADO = "EQUIPAMENTO_MODELO_CRIADO"
EQUIPAMENTO_MODELO_ATUALIZADO = "EQUIPAMENTO_MODELO_ATUALIZADO"
EQUIPAMENTO_MODELO_DESATIVADO = "EQUIPAMENTO_MODELO_DESATIVADO"
OS_EQUIPAMENTO_VINCULADO = "OS_EQUIPAMENTO_VINCULADO"
OS_EQUIPAMENTO_ALTERADO = "OS_EQUIPAMENTO_ALTERADO"
OS_EQUIPAMENTO_REMOVIDO = "OS_EQUIPAMENTO_REMOVIDO"
SERVICO_ATUALIZADO = "SERVICO_ATUALIZADO"
CONSERTO_SALVO = "CONSERTO_SALVO"
CONFLITO_ADMINISTRATIVO = "CONFLITO_ADMINISTRATIVO"  # SY-05 (ator: sistema)
FOTO_CORRIGIDA_ADMIN = "FOTO_CORRIGIDA_ADMIN"
MATERIAIS_CORRIGIDOS_ADMIN = "MATERIAIS_CORRIGIDOS_ADMIN"


def registrar_acao(db: Session, *, id_os: Optional[int], usuario: Optional[Dict[str, Any]], acao: str,
                   payload: Optional[Dict[str, Any]] = None) -> None:
    """Adiciona uma linha em `log_acao` à sessão (sem commit) e emite o log da aplicação."""
    id_usuario = usuario.get("user_id") if usuario else None
    papel = usuario.get("role") if usuario else "sistema"
    logger.info("acao=%s os=%s usuario=%s papel=%s", acao, id_os, id_usuario, papel)
    try:
        from app.models.log_acao import LogAcao
    except ImportError:  # pragma: no cover - modelo ainda não disponível neste ambiente
        logger.warning("Modelo LogAcao indisponível; ação %s da OS %s registrada apenas em log.", acao, id_os)
        return
    db.add(LogAcao(id_os=id_os, id_usuario=id_usuario, papel=papel, acao=acao, payload=payload))
