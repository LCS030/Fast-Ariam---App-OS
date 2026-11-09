"""
Fluxo da visita (SDD 6.6, RN-16..RN-27, RF-14): deslocamentos, atendimento, pausa e finalização da volta.

Cada função aplica TODAS as validações antes de alterar a sessão e confirma a transação UMA vez no final
(visita + OS + pausa + custo + auditoria). Em caso de erro faz rollback.

Horários (AR-05 / RN-24 / PR-30): cada ação grava o momento em TIMESTAMPTZ (`*_em`) - o `ocorrido_em` enviado pelo
aparelho quando houver, senão o instante atual do servidor (UTC) - e mantém a coluna legada `hora_*` (HH:mm)
derivada, para os fronts atuais. HH:mm é o horário de parede no fuso do próprio `ocorrido_em` (ou do servidor).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.validators import cpf_valido, normalizar_cpf
from app.repositories.supabase_repository import SQLRepository
from app.schemas.base_schemas import StatusChamado
from app.services import auditoria_service as auditoria
from app.services import custo_service, equipamento_service, file_service, integridade_service
from app.services.tempo import agora_utc, data_negocio, hhmm_negocio
from app.services.chamado_service import AcaoOS, exigir_status, validar_transicao

logger = logging.getLogger(__name__)

# marco -> (coluna TIMESTAMPTZ, coluna legada HH:mm)
_MARCOS = {
    "ida_inicio": ("ida_inicio_em", "hora_inicio_ida"),
    "ida_fim": ("ida_fim_em", "hora_fim_ida"),
    "atendimento_inicio": ("atendimento_inicio_em", "hora_inicio_atendimento"),
    "atendimento_fim": ("atendimento_fim_em", "hora_fim_atendimento"),
    "volta_inicio": ("volta_inicio_em", "hora_inicio_volta"),
    "volta_fim": ("volta_fim_em", "hora_fim_volta"),
}


# ---------------------------------------------------------------------------------------------------------------------
# Marcos de tempo
# ---------------------------------------------------------------------------------------------------------------------

def _limpo(valor):
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


def marco(visita, nome: str):
    """Valor do marco (TIMESTAMPTZ ou, em dados legados, o HH:mm). None se a etapa ainda não ocorreu."""
    col_em, col_hora = _MARCOS[nome]
    return getattr(visita, col_em, None) or _limpo(getattr(visita, col_hora, None))


def _como_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _momento(ocorrido_em: Optional[datetime]) -> Tuple[datetime, str]:
    """(instante timezone-aware, HH:mm legado)."""
    # O instante é guardado em UTC; o HH:mm legado é derivado no fuso de negócio America/Sao_Paulo (D6).
    instante = ocorrido_em.astimezone(timezone.utc) if ocorrido_em is not None else agora_utc()
    return instante, hhmm_negocio(instante)


def _registrar_marco(visita, nome: str, momento: datetime, hhmm: str, *, depois_de: Optional[str] = None) -> None:
    """Grava o marco. Rejeita (400) um instante anterior ao marco que deveria precedê-lo."""
    if depois_de is not None:
        anterior = getattr(visita, _MARCOS[depois_de][0], None)
        if anterior is not None and _como_utc(momento) < _como_utc(anterior):
            raise HTTPException(status_code=400,
                                detail="O horário informado (ocorrido_em) é anterior ao da etapa anterior.")
    col_em, col_hora = _MARCOS[nome]
    setattr(visita, col_em, momento)
    setattr(visita, col_hora, hhmm)


def pausa_ativa(repo: SQLRepository, visita_id: int):
    """Última pausa ativa da visita, ou None."""
    ativas = [p for p in repo.get_pausas_by_visita(visita_id) if p.is_ativa]
    return ativas[-1] if ativas else None


def visita_vigente(repo: SQLRepository, chamado, visita) -> bool:
    """
    Só a visita MAIS RECENTE da OS é executável. Visitas anteriores ficam como histórico: finalizadas por
    reagendamento ou abandonadas quando o técnico foi desativado (RN-08a). OS Pendente (sem técnico) não executa nada.
    """
    ultima = repo.get_ultima_visita(chamado.id_os)
    status = chamado.status.value if hasattr(chamado.status, "value") else str(chamado.status)
    return (ultima is not None and ultima.id_visita == visita.id_visita
            and status != StatusChamado.PENDENTE.value)


def exigir_visita_vigente(repo: SQLRepository, chamado, visita) -> None:
    """409 ao tentar executar ação de campo em visita encerrada/abandonada/substituída ou em OS Pendente."""
    if not visita_vigente(repo, chamado, visita):
        raise HTTPException(
            status_code=409,
            detail=("Esta visita não é mais executável (encerrada, substituída por outra visita ou OS sem técnico). "
                    "Use a visita aberta atual da OS."))


# ---------------------------------------------------------------------------------------------------------------------
# Estado (GET .../estado) - fonte de verdade dos botões do app
# ---------------------------------------------------------------------------------------------------------------------

def calcular_estado(repo: SQLRepository, chamado, visita) -> Dict[str, Any]:
    ida_ini, ida_fim = marco(visita, "ida_inicio"), marco(visita, "ida_fim")
    at_ini, at_fim = marco(visita, "atendimento_inicio"), marco(visita, "atendimento_fim")
    vo_ini, vo_fim = marco(visita, "volta_inicio"), marco(visita, "volta_fim")
    pausa = pausa_ativa(repo, visita.id_visita)
    is_pausada = pausa is not None
    status = chamado.status.value if hasattr(chamado.status, "value") else str(chamado.status)
    finalizada = bool(visita.servico_finalizado)

    vigente = visita_vigente(repo, chamado, visita)
    if not vigente:
        # Visita de histórico (abandonada/substituída) ou OS Pendente: nenhum botão de ação.
        return {
            "pode_iniciar_deslocamento_ida": False, "pode_finalizar_deslocamento_ida": False,
            "pode_iniciar_atendimento": False, "pode_finalizar_atendimento": False,
            "pode_iniciar_deslocamento_volta": False, "pode_finalizar_deslocamento_volta": False,
            "pode_concluir_chamado": vo_fim is not None, "pode_pausar_os": False,
            "is_os_pausada": is_pausada, "motivo_pausa": pausa.motivo if pausa else None,
            "visita_vigente": False,
            # v0.5: sem visita executável não há pendências a exibir.
            "pode_registrar_foto_defeito": False, "atendimento_em_andamento": False,
            "bloqueio_iniciar_atendimento": None, "bloqueio_finalizar_atendimento": None, "equipamentos": [],
        }

    em_atendimento = at_ini is not None and at_fim is None and not finalizada
    # v0.5 (TR-12 / TR-13): as travas de foto de defeito e de conserto também comandam os botões do app.
    avaliacao = equipamento_service.avaliar_visita(repo, chamado, visita)
    bloqueio_ini = equipamento_service.bloqueio_iniciar(avaliacao)
    bloqueio_fim = equipamento_service.bloqueio_finalizar(avaliacao)
    base_iniciar = (ida_fim is not None and at_ini is None and not finalizada
                    and status == StatusChamado.AGENDADO.value)
    base_finalizar = em_atendimento and not is_pausada
    return {
        "visita_vigente": True,
        # 1) Ida
        "pode_iniciar_deslocamento_ida": ida_ini is None and not finalizada
        and status == StatusChamado.AGENDADO.value,
        "pode_finalizar_deslocamento_ida": ida_ini is not None and ida_fim is None,
        # 2) Atendimento
        "pode_iniciar_atendimento": base_iniciar and bloqueio_ini is None,
        "pode_finalizar_atendimento": base_finalizar and bloqueio_fim is None,
        # v0.5: a foto do defeito é registrada ANTES de iniciar o atendimento (RN-43) e também durante ele.
        "pode_registrar_foto_defeito": (not finalizada and at_fim is None
                                        and status in (StatusChamado.AGENDADO.value, StatusChamado.EM_ATENDIMENTO.value)),
        "atendimento_em_andamento": em_atendimento,
        # Texto exato que o servidor devolveria com 409; null quando não há bloqueio nessa etapa.
        "bloqueio_iniciar_atendimento": bloqueio_ini if base_iniciar else None,
        "bloqueio_finalizar_atendimento": bloqueio_fim if base_finalizar else None,
        "equipamentos": avaliacao["equipamentos"],
        # 3) Volta: após o fim do atendimento OU com a visita pausada (RN-18)
        "pode_iniciar_deslocamento_volta": vo_ini is None and not finalizada
        and (at_fim is not None or (is_pausada and at_ini is not None)),
        "pode_finalizar_deslocamento_volta": vo_ini is not None and vo_fim is None,
        # 4) Legado do contrato: a OS conclui sozinha ao finalizar a volta (não há conclusão manual)
        "pode_concluir_chamado": vo_fim is not None,
        # Pausa (RN-26)
        "pode_pausar_os": em_atendimento and not is_pausada,
        "is_os_pausada": is_pausada,
        "motivo_pausa": pausa.motivo if pausa else None,
    }


# ---------------------------------------------------------------------------------------------------------------------
# Deslocamento
# ---------------------------------------------------------------------------------------------------------------------

def _recalcular_km_total(visita) -> int:
    """km_total = (km_fim_ida - km_inicio_ida) + (km_fim_volta - km_inicio_volta), perna ausente conta 0 (SDD 4.7)."""
    def perna(ini, fim):
        return (fim - ini) if ini is not None and fim is not None else 0

    return perna(visita.km_inicio_ida, visita.km_fim_ida) + perna(visita.km_inicio_volta, visita.km_fim_volta)


def iniciar_deslocamento(repo: SQLRepository, chamado, visita, tipo: str, km_inicio: int,
                         ocorrido_em: Optional[datetime]) -> Dict[str, Any]:
    exigir_visita_vigente(repo, chamado, visita)
    momento, hhmm = _momento(ocorrido_em)
    if tipo == "ida":
        exigir_status(chamado, frozenset({StatusChamado.AGENDADO}), "iniciar o deslocamento de ida")
        if marco(visita, "ida_inicio") is not None:
            raise HTTPException(status_code=400, detail="Deslocamento de ida já iniciado")
        visita.km_inicio_ida = km_inicio
        _registrar_marco(visita, "ida_inicio", momento, hhmm)
    else:
        exigir_status(chamado, frozenset({StatusChamado.EM_ATENDIMENTO, StatusChamado.PAUSADO}),
                      "iniciar o deslocamento de volta")
        # RN-18: depois do fim do atendimento, EXCETO com a visita pausada.
        if marco(visita, "atendimento_fim") is None and pausa_ativa(repo, visita.id_visita) is None:
            raise HTTPException(status_code=400,
                                detail="Finalize o atendimento antes de iniciar o deslocamento de volta")
        if marco(visita, "volta_inicio") is not None:
            raise HTTPException(status_code=400, detail="Deslocamento de volta já iniciado")
        visita.km_inicio_volta = km_inicio
        _registrar_marco(visita, "volta_inicio", momento, hhmm)
    try:
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return {"message": "Deslocamento iniciado com sucesso", "tipo": tipo, "km_inicio": km_inicio,
            "hora_inicio": hhmm, "iniciado_em": momento.isoformat()}


def _validar_evidencias_finalizacao(visita, km_total: int) -> None:
    """RN-19 / RN-20 / T-07: evidências obrigatórias para encerrar a visita."""
    if km_total > 0:
        inicio = visita.odometro_inicio_url or visita.foto_inicio_ida_url
        fim = visita.odometro_fim_url or visita.foto_fim_volta_url
        if not inicio or not fim:
            raise HTTPException(
                status_code=400,
                detail=("Fotos do odômetro de início e fim são obrigatórias se km_total > 0 "
                        "(envie foto_inicio_ida e foto_fim_volta antes de finalizar a volta)."))
    if float(visita.valor_pedagio or 0) > 0 and not visita.comprovante_pedagio_urls:
        raise HTTPException(status_code=400,
                            detail="Comprovante(s) de pedágio são obrigatórios se valor_pedagio > 0.")
    if float(visita.valor_frete_devolucao or 0) > 0 and not visita.comprovante_frete_urls:
        raise HTTPException(status_code=400,
                            detail="Comprovante(s) de frete são obrigatórios se valor_frete_devolucao > 0.")


def finalizar_deslocamento(repo: SQLRepository, chamado, visita, tipo: str, km_fim: int,
                           ocorrido_em: Optional[datetime], usuario: dict):
    """Ida: apenas fecha o trajeto. Volta: encerra a visita e decide o destino da OS (RF-14 / TR-02 / TR-05)."""
    exigir_visita_vigente(repo, chamado, visita)
    momento, hhmm = _momento(ocorrido_em)

    if tipo == "ida":
        if marco(visita, "ida_inicio") is None:
            raise HTTPException(status_code=400, detail="Deslocamento de ida não foi iniciado")
        if marco(visita, "ida_fim") is not None:
            raise HTTPException(status_code=400, detail="Deslocamento de ida já foi finalizado")
        if visita.km_inicio_ida is not None and km_fim < visita.km_inicio_ida:
            raise HTTPException(status_code=400, detail="km_fim não pode ser menor que km_inicio da ida.")
        visita.km_fim_ida = km_fim
        _registrar_marco(visita, "ida_fim", momento, hhmm, depois_de="ida_inicio")
        visita.km_total = _recalcular_km_total(visita)
        try:
            repo.commit()
        except Exception:
            repo.rollback()
            raise
        return repo.get_visita_by_id(visita.id_visita)

    # ----- volta -----
    # D11: trava a OS e relê visita/OS do banco; duas finalizações concorrentes ficam serializadas e a segunda vê o
    # estado já finalizado (cai em "volta já finalizada").
    chamado = repo.lock_chamado(chamado.id_os) or chamado
    repo.db.refresh(visita)
    if marco(visita, "volta_inicio") is None:
        raise HTTPException(status_code=400, detail="Deslocamento de volta não foi iniciado")
    if marco(visita, "volta_fim") is not None:
        raise HTTPException(status_code=400, detail="Deslocamento de volta já foi finalizado")
    if visita.km_inicio_volta is not None and km_fim < visita.km_inicio_volta:
        raise HTTPException(status_code=400, detail="km_fim não pode ser menor que km_inicio da volta.")

    pausada = pausa_ativa(repo, visita.id_visita) is not None
    acao = AcaoOS.FINALIZAR_VOLTA_COM_PAUSA if pausada else AcaoOS.FINALIZAR_VOLTA_SEM_PAUSA
    status_destino = validar_transicao(chamado.status, acao)  # 409

    # Calcula o km_total COM o km_fim informado e valida as evidências antes de tocar na sessão.
    km_fim_anterior = visita.km_fim_volta
    visita.km_fim_volta = km_fim
    km_total = _recalcular_km_total(visita)
    try:
        _validar_evidencias_finalizacao(visita, km_total)
    except HTTPException:
        visita.km_fim_volta = km_fim_anterior
        repo.rollback()
        raise

    try:
        _registrar_marco(visita, "volta_fim", momento, hhmm, depois_de="volta_inicio")
        visita.km_total = km_total
        visita.servico_finalizado = True
        dados_os: Dict[str, Any] = {"status": status_destino}
        if not pausada:
            dados_os["data_conclusao"] = data_negocio(momento)
        repo.update_chamado(chamado.id_os, dados_os, commit=False)

        if pausada:
            # A pausa continua ativa até o admin reagendar (T-02).
            auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario,
                                     acao=auditoria.OS_AGUARDANDO_REAGENDAMENTO,
                                     payload={"id_visita": visita.id_visita, "km_total": km_total})
        else:
            repo.flush()
            repo.db.refresh(chamado)  # garante visitas/serviços atuais para o cálculo
            custo = custo_service.congelar_custo(repo.db, chamado)
            auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.OS_FINALIZADA,
                                     payload={"id_visita": visita.id_visita, "km_total": km_total,
                                              "custo_total": custo.total_geral})
        repo.commit()
    except IntegrityError:
        # custo_os duplicado (PK = id_os): outra finalização concorrente já gravou o snapshot. Idempotente se a
        # visita/OS estão de fato finalizadas; senão é um conflito real.
        visita_id, chamado_id = visita.id_visita, chamado.id_os
        repo.rollback()
        atual = repo.get_visita_by_id(visita_id)
        os_atual = repo.get_chamado_by_id(chamado_id)
        if (atual is not None and atual.servico_finalizado and os_atual is not None
                and os_atual.status == StatusChamado.FINALIZADO):
            logger.info("Finalização da OS %s já efetivada por outra requisição; resposta idempotente.", chamado_id)
            return atual
        raise HTTPException(status_code=409, detail="Conflito ao finalizar a OS; tente novamente.")
    except Exception:
        repo.rollback()
        raise
    return repo.get_visita_by_id(visita.id_visita)


# ---------------------------------------------------------------------------------------------------------------------
# Atendimento
# ---------------------------------------------------------------------------------------------------------------------

def iniciar_atendimento(repo: SQLRepository, chamado, visita, ocorrido_em: Optional[datetime], usuario: dict):
    """RN-17 / PR-36: exige ida FINALIZADA (400) e OS Agendado (409). OS -> Em Atendimento."""
    exigir_visita_vigente(repo, chamado, visita)
    if marco(visita, "atendimento_inicio") is not None:
        raise HTTPException(status_code=400, detail="Atendimento já foi iniciado.")
    if marco(visita, "ida_fim") is None:
        raise HTTPException(status_code=400,
                            detail="Finalize o deslocamento de ida antes de iniciar o atendimento.")
    destino = validar_transicao(chamado.status, AcaoOS.INICIAR_ATENDIMENTO)  # 409 se não for Agendado
    # TR-12 / RN-43 (v0.5): foto de defeito de cada equipamento da OS na visita; OS legada sem equipamento (RN-46).
    # Trava a OS e relê do banco: vincular/remover equipamento e iniciar o atendimento ficam serializados.
    chamado = repo.lock_chamado(chamado.id_os) or chamado
    equipamento_service.exigir_pronto_para_iniciar(repo, chamado, visita)

    momento, hhmm = _momento(ocorrido_em)
    try:
        _registrar_marco(visita, "atendimento_inicio", momento, hhmm, depois_de="ida_fim")
        repo.update_chamado(chamado.id_os, {"status": destino}, commit=False)
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.ATENDIMENTO_INICIADO,
                                 payload={"id_visita": visita.id_visita,
                                          "equipamentos_conferidos": [e.id_os_equipamento for e in
                                                                      repo.get_os_equipamentos(chamado.id_os)]})
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return repo.get_visita_by_id(visita.id_visita)


def pausar(repo: SQLRepository, chamado, visita, motivo: str, descricao: Optional[str],
           ocorrido_em: Optional[datetime], usuario: dict):
    """RN-26 / RN-29 / RN-30: visita em atendimento e não finalizada; não pausa duas vezes; OS -> Pausado."""
    exigir_visita_vigente(repo, chamado, visita)
    if (marco(visita, "atendimento_inicio") is None or marco(visita, "atendimento_fim") is not None
            or visita.servico_finalizado):
        raise HTTPException(status_code=400, detail="Só é possível pausar uma visita que esteja em atendimento.")
    if pausa_ativa(repo, visita.id_visita) is not None:
        raise HTTPException(status_code=400, detail="A visita já está pausada.")
    destino = validar_transicao(chamado.status, AcaoOS.PAUSAR)  # 409 se não estiver Em Atendimento

    momento, _ = _momento(ocorrido_em)
    try:
        pausa = repo.create_pausa(
            visita.id_visita,
            {"motivo": motivo, "descricao": descricao, "criado_em": momento},
            por_usuario_id=usuario.get("user_id"), por_papel=usuario.get("role"), commit=False)
        repo.update_chamado(chamado.id_os, {"status": destino}, commit=False)
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.OS_PAUSADA,
                                 payload={"id_visita": visita.id_visita, "motivo": motivo})
        repo.commit()
        repo.db.refresh(pausa)
    except Exception:
        repo.rollback()
        raise
    return pausa


def finalizar_atendimento(repo: SQLRepository, chamado, visita, nome_cliente: str, documento_cliente: str,
                          assinatura_base64: Optional[str], ocorrido_em: Optional[datetime], usuario: dict,
                          assinatura_url: Optional[str] = None,
                          assinatura_sha256: Optional[str] = None) -> Dict[str, str]:
    """
    RN-22 / RN-23 / PR-10 / PR-35: grava nome, CPF (só dígitos) e assinatura NA VISITA. Bloqueia com pausa ativa (400).
    O status da OS não muda: ela segue Em Atendimento até a volta.

    Integridade: grava o SHA-256 da assinatura e o SELO HMAC da visita (integridade_service) antes do commit.
    `assinatura_sha256`: no envio online é o hash informado pelo aparelho (conferido contra os bytes, 422 se divergir);
    na sincronização (`assinatura_url` presente) é o hash já calculado pelo servidor ao receber o arquivo.
    """
    exigir_visita_vigente(repo, chamado, visita)
    if pausa_ativa(repo, visita.id_visita) is not None:
        raise HTTPException(status_code=400,
                            detail="Não é possível finalizar o atendimento enquanto a OS estiver pausada.")
    if marco(visita, "atendimento_inicio") is None:
        raise HTTPException(status_code=400, detail="O atendimento ainda não foi iniciado.")
    if marco(visita, "atendimento_fim") is not None:
        raise HTTPException(status_code=400, detail="Atendimento já foi finalizado.")
    if not cpf_valido(documento_cliente):
        raise HTTPException(status_code=422, detail="CPF inválido")
    # `assinatura_url` (sincronização offline): o arquivo já foi recebido e validado em /api/sync/arquivos.
    imagem = (None if assinatura_url
              else file_service.decodificar_assinatura(assinatura_base64, assinatura_sha256))  # 400 / 413 / 422 (hash)
    sha_assinatura = assinatura_sha256 if assinatura_url else imagem.sha256
    # TR-13 / RN-44 (v0.5): conserto salvo + foto de conserto de cada equipamento, ANTES de gravar a assinatura.
    chamado = repo.lock_chamado(chamado.id_os) or chamado
    equipamento_service.exigir_pronto_para_finalizar(repo, chamado, visita)

    momento, hhmm = _momento(ocorrido_em)
    criou_arquivo = False
    try:
        _registrar_marco(visita, "atendimento_fim", momento, hhmm, depois_de="atendimento_inicio")
        if not assinatura_url:
            assinatura_url = file_service.salvar_assinatura(imagem)
            criou_arquivo = True
        visita.assinatura_url = assinatura_url
        visita.assinatura_sha256 = sha_assinatura
        visita.nome_cliente_assinatura = nome_cliente
        visita.documento_cliente = normalizar_cpf(documento_cliente)
        # Selo HMAC no mesmo commit da finalização. Também vai para o log_acao (2ª cópia): se alguém anular o selo da
        # visita no banco, a verificação acusa "selo_removido" em vez de tratar como legado.
        selo = integridade_service.selar_visita(repo.db, chamado, visita)
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario,
                                 acao=auditoria.ATENDIMENTO_FINALIZADO,
                                 payload={"id_visita": visita.id_visita,
                                          "equipamentos_conferidos": [e.id_os_equipamento for e in
                                                                      repo.get_os_equipamentos(chamado.id_os)],
                                          "selo": selo, "selo_versao": integridade_service.SELO_VERSAO})
        repo.commit()
    except Exception:
        repo.rollback()
        if criou_arquivo:  # nunca apaga o arquivo recebido pela sincronização: ele fica rastreável (SY-06)
            file_service.remover_arquivo_por_url(assinatura_url)
        raise
    return {"status": "ok", "assinatura_url": assinatura_url}
