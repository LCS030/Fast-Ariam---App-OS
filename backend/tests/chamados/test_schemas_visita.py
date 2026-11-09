"""
Schemas de Visita (PR-11 / T-10) e unificação VisitaBase/Create/Update (SDD seção 7).
"""
import pytest
from pydantic import ValidationError

from app.schemas.base_schemas import MotivoPausa
from app.schemas.visita import FinalizarAtendimentoPayload, PausarPayload, Visita, VisitaCreate, VisitaUpdate


def test_visita_de_resposta_tolera_campos_vazios():
    v = Visita.model_validate({"id_visita": 1, "data_visita": "2026-11-10", "km_total": 0})
    assert v.hora_inicio_ida is None and v.ida_inicio_em is None and v.servicos_realizados == []
    assert v.km_total == 0 and v.valor_pedagio == 0.0


def test_visita_de_resposta_rejeita_km_total_negativo():
    with pytest.raises(ValidationError):
        Visita.model_validate({"id_visita": 1, "data_visita": "2026-11-10", "km_total": -1})


def test_create_exige_apenas_data_e_nao_aceita_km_total_como_entrada():
    c = VisitaCreate.model_validate({"data_visita": "2026-11-10", "km_total": 999, "nome_ajudante": "x"})
    assert not hasattr(c, "km_total") and not hasattr(c, "nome_ajudante")  # servidor calcula km; sem ajudantes
    with pytest.raises(ValidationError):
        VisitaCreate.model_validate({})


def test_update_e_parcial_e_nao_aceita_horarios_nem_km():
    u = VisitaUpdate.model_validate({"valor_pedagio": 5, "hora_fim_ida": "10:00", "km_total": 10})
    assert u.model_dump(exclude_unset=True) == {"valor_pedagio": 5.0}
    with pytest.raises(ValidationError):
        VisitaUpdate.model_validate({"valor_pedagio": -1})


def test_pausar_payload_valida_motivo_e_outro():
    assert PausarPayload(motivo="Peça pendente").motivo is MotivoPausa.PECA_PENDENTE
    with pytest.raises(ValidationError):
        PausarPayload(motivo="Almoço")
    with pytest.raises(ValidationError):
        PausarPayload(motivo="Outro")
    assert PausarPayload(motivo="Outro", descricao=" aguardando ").descricao == "aguardando"


def test_finalizar_atendimento_payload_exige_campos():
    with pytest.raises(ValidationError):
        FinalizarAtendimentoPayload(nome_cliente="x", documento_cliente="y")


def test_lista_de_motivos_e_a_oficial():
    assert [m.value for m in MotivoPausa] == [
        "Peça pendente", "Cliente ausente", "Condições inseguras", "Aguardando aprovação", "Outro"]
