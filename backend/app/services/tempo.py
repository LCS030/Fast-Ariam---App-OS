"""
Fuso de negócio (D6): datas "de calendário" (data_abertura, data_conclusao, data_visita padrão) e os horários HH:mm
legados são derivados em America/Sao_Paulo, não no fuso do servidor (que em cloud costuma ser UTC).
Os instantes `*_em` continuam gravados em UTC.
"""
import logging
from datetime import date, datetime, timedelta, timezone, tzinfo

logger = logging.getLogger(__name__)

NOME_FUSO_NEGOCIO = "America/Sao_Paulo"


def _carregar_fuso() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(NOME_FUSO_NEGOCIO)
    except Exception:  # sem tzdata (ex.: Windows sem o pacote `tzdata`)
        logger.warning("tzdata indisponível; usando UTC-03:00 fixo (Brasil sem horário de verão desde 2019). "
                       "Instale o pacote `tzdata`.")
        return timezone(timedelta(hours=-3))


FUSO_NEGOCIO: tzinfo = _carregar_fuso()


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def hoje_negocio() -> date:
    return datetime.now(FUSO_NEGOCIO).date()


def data_negocio(momento: datetime) -> date:
    """Data de calendário de um instante no fuso de negócio (naive é tratado como UTC)."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO_NEGOCIO).date()


def hhmm_negocio(momento: datetime) -> str:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO_NEGOCIO).strftime("%H:%M")
