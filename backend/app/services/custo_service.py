"""
Cálculo e congelamento do custo da OS (SDD 6.11, RF-19, RN-31..RN-33).

* O custo é registro INTERNO (não é cobrado do cliente).
* Valores de referência são GLOBAIS: lidos de `configuracao_custo` (linha única) com fallback para
  `VALORES_ASSISTENCIA` de core/config.py. Não há valor por técnico e o técnico não altera nada.
* Ajudantes estão fora do escopo (RN-25): não entram no cálculo.
* Na finalização da OS o resultado e os valores usados são gravados em `custo_os` (snapshot). Para OS Finalizada,
  `GET /custos` devolve o snapshot, nunca recalcula (CA-19).

Fórmula por visita:
  materiais      = soma(quantidade * valor)
  km             = km_total * quilometragem
  pedágio/frete  = valores informados
  deslocamento   = horas(ida) + horas(volta)  *  tempo_deslocamento_tecnico        [ver dúvida ao PO]
  serviço        = 0 se não houve atendimento; horas <= 1 -> primeira_hora_tecnico;
                   horas  > 1 -> primeira_hora_tecnico + (horas - 1) * hora_tecnico          (RN-31)

D7 (decisão do PO): visita PAUSADA, ou atendimento que nunca foi finalizado (ex.: visita abandonada pela desativação
do técnico, RN-08a), tem tempo de serviço ZERO: o atendimento só conta com início E fim registrados. O mesmo critério
vale para as demais parcelas: visitas encerradas/abandonadas contam SOMENTE o que foi registrado (km_total parcial,
trechos de deslocamento com início e fim, materiais lançados, pedágio/frete informados).
"""
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import VALORES_ASSISTENCIA
from app.schemas.custo import CustoMaterialDetalhado, CustoTotalResponse, CustoVisitaDetalhado

logger = logging.getLogger(__name__)

# chave em configuracao_custo -> chave legada em config.VALORES_ASSISTENCIA
_CHAVES_CONFIG = {
    "primeira_hora_tecnico": "PRIMEIRA_HORA_TECNICO",
    "hora_tecnico": "HORA_TECNICO",
    "tempo_deslocamento_tecnico": "TEMPO_DESLOCAMENTO_TECNICO",
    "quilometragem": "QUILOMETRAGEM",
}


def valores_padrao_config() -> Dict[str, float]:
    """Fallback: valores de core/config.py (leitura apenas)."""
    return {k: float(VALORES_ASSISTENCIA[legado]) for k, legado in _CHAVES_CONFIG.items()}


def obter_valores_globais(db: Optional[Session]) -> Dict[str, float]:
    """
    Valores globais de custo. A linha de `configuracao_custo` tem precedência; sem sessão, sem linha ou sem a tabela,
    usa o fallback de config.py (a linha não é semeada pela migração: ver models/configuracao_custo.py).
    """
    if db is not None:
        try:
            from app.models.configuracao_custo import ConfiguracaoCusto
            linha = db.get(ConfiguracaoCusto, 1)
            if linha is not None:
                return {k: float(getattr(linha, k)) for k in _CHAVES_CONFIG}
        except Exception:  # tabela inexistente / erro de leitura não pode impedir o cálculo
            logger.warning("Falha ao ler configuracao_custo; usando valores de config.py.", exc_info=True)
    return valores_padrao_config()


# ---------------------------------------------------------------------------------------------------------------------
# Durações
# ---------------------------------------------------------------------------------------------------------------------

def _como_utc(valor: datetime) -> datetime:
    """Compara datetimes de forma segura: valores sem fuso (SQLite) são tratados como UTC."""
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)


def _horas_entre(inicio_em, fim_em, hora_inicio: Optional[str], hora_fim: Optional[str]) -> float:
    """Horas decimais entre dois momentos; usa HH:mm legado quando não há TIMESTAMPTZ. Nunca negativo."""
    if inicio_em is not None and fim_em is not None:
        return max((_como_utc(fim_em) - _como_utc(inicio_em)).total_seconds() / 3600, 0.0)
    if hora_inicio and hora_fim:
        try:
            t_ini = datetime.strptime(hora_inicio.strip(), "%H:%M")
            t_fim = datetime.strptime(hora_fim.strip(), "%H:%M")
            return max((t_fim - t_ini).total_seconds() / 3600, 0.0)
        except ValueError:
            return 0.0
    return 0.0


class CustoService:
    def __init__(self, valores: Optional[Dict[str, float]] = None, db: Optional[Session] = None):
        self.valores = valores if valores is not None else obter_valores_globais(db)

    # ----------------------------------------------------------------------------------------------------------
    # Conversão ORM -> dict
    # ----------------------------------------------------------------------------------------------------------
    @staticmethod
    def chamado_para_dict(chamado) -> Dict[str, Any]:
        """Extrai do ORM só o que o cálculo usa (chaves corretas: id_os / id_visita - PR-12)."""
        visitas = []
        for v in sorted(chamado.visitas, key=lambda x: x.id_visita):
            visitas.append({
                "id_visita": v.id_visita,
                "data_visita": v.data_visita,
                "km_total": v.km_total or 0,
                "valor_pedagio": float(v.valor_pedagio or 0),
                "valor_frete_devolucao": float(v.valor_frete_devolucao or 0),
                "ida_inicio_em": getattr(v, "ida_inicio_em", None),
                "ida_fim_em": getattr(v, "ida_fim_em", None),
                "volta_inicio_em": getattr(v, "volta_inicio_em", None),
                "volta_fim_em": getattr(v, "volta_fim_em", None),
                "atendimento_inicio_em": getattr(v, "atendimento_inicio_em", None),
                "atendimento_fim_em": getattr(v, "atendimento_fim_em", None),
                "hora_inicio_ida": v.hora_inicio_ida, "hora_fim_ida": v.hora_fim_ida,
                "hora_inicio_volta": v.hora_inicio_volta, "hora_fim_volta": v.hora_fim_volta,
                "hora_inicio_atendimento": v.hora_inicio_atendimento,
                "hora_fim_atendimento": v.hora_fim_atendimento,
                "hora_inicio_deslocamento": v.hora_inicio_deslocamento,
                "hora_chegada_cliente": v.hora_chegada_cliente,
                "servicos_realizados": [{
                    "materiais_utilizados": [
                        {"nome": m.nome, "quantidade": m.quantidade, "valor": float(m.valor)}
                        for m in s.materiais_utilizados]
                } for s in v.servicos_realizados],
            })
        return {"id_os": chamado.id_os, "visitas": visitas}

    # ----------------------------------------------------------------------------------------------------------
    # Cálculo
    # ----------------------------------------------------------------------------------------------------------
    def _horas_deslocamento(self, visita: Dict[str, Any]) -> float:
        ida = _horas_entre(visita.get("ida_inicio_em"), visita.get("ida_fim_em"),
                           visita.get("hora_inicio_ida"), visita.get("hora_fim_ida"))
        volta = _horas_entre(visita.get("volta_inicio_em"), visita.get("volta_fim_em"),
                             visita.get("hora_inicio_volta"), visita.get("hora_fim_volta"))
        if ida == 0.0 and volta == 0.0:
            # Dados legados (antes do fluxo ida/volta): início do deslocamento até a chegada ao cliente.
            return _horas_entre(None, None, visita.get("hora_inicio_deslocamento"), visita.get("hora_chegada_cliente"))
        return ida + volta

    def _custo_servico(self, horas_servico: float) -> float:
        if horas_servico <= 0:
            return 0.0
        primeira = self.valores["primeira_hora_tecnico"]
        if horas_servico <= 1:
            return primeira
        return primeira + (horas_servico - 1) * self.valores["hora_tecnico"]

    def calcular_custo_chamado(self, chamado: Dict[str, Any]) -> CustoTotalResponse:
        total_materiais = total_km = total_pedagio = total_frete = total_servico = total_desloc = 0.0
        detalhes_por_visita = []
        materiais_compilado: Dict[str, Dict[str, Any]] = {}

        for visita in chamado.get("visitas", []):
            custo_materiais = 0.0
            for servico in visita.get("servicos_realizados", []):
                for material in servico.get("materiais_utilizados", []):
                    qnt, val = material.get("quantidade", 0) or 0, material.get("valor", 0) or 0
                    subtotal = round(qnt * val, 2)
                    custo_materiais += subtotal
                    nome = material.get("nome", "Desconhecido")
                    acc = materiais_compilado.setdefault(nome, {"qnt": 0, "val_unit": val, "total": 0.0})
                    acc["qnt"] += qnt
                    acc["total"] += subtotal
            custo_materiais = round(custo_materiais, 2)

            custo_km = round((visita.get("km_total") or 0) * self.valores["quilometragem"], 2)
            custo_pedagio = round(visita.get("valor_pedagio") or 0.0, 2)
            custo_frete = round(visita.get("valor_frete_devolucao") or 0.0, 2)
            custo_desloc = round(self._horas_deslocamento(visita) * self.valores["tempo_deslocamento_tecnico"], 2)
            horas_servico = _horas_entre(visita.get("atendimento_inicio_em"), visita.get("atendimento_fim_em"),
                                         visita.get("hora_inicio_atendimento"), visita.get("hora_fim_atendimento"))
            custo_servico = round(self._custo_servico(horas_servico), 2)

            subtotal_visita = round(custo_materiais + custo_km + custo_pedagio + custo_frete + custo_desloc
                                    + custo_servico, 2)
            data_visita = visita.get("data_visita")
            detalhes_por_visita.append(CustoVisitaDetalhado(
                id_visita=visita.get("id_visita", 0),
                data=data_visita if isinstance(data_visita, date) else date.fromisoformat(str(data_visita)),
                custo_total_materiais=custo_materiais, custo_km=custo_km, custo_pedagio=custo_pedagio,
                custo_frete=custo_frete, custo_tempo_servico=custo_servico, custo_tempo_deslocamento=custo_desloc,
                subtotal_visita=subtotal_visita))

            total_materiais += custo_materiais
            total_km += custo_km
            total_pedagio += custo_pedagio
            total_frete += custo_frete
            total_servico += custo_servico
            total_desloc += custo_desloc

        detalhes_materiais = [
            CustoMaterialDetalhado(nome=nome, quantidade=d["qnt"], valor_unitario=d["val_unit"],
                                   valor_total=round(d["total"], 2))
            for nome, d in materiais_compilado.items()]

        return CustoTotalResponse(
            id_os=chamado.get("id_os", 0),
            custo_total_materiais=round(total_materiais, 2),
            custo_total_km=round(total_km, 2),
            custo_total_pedagio=round(total_pedagio, 2),
            custo_total_frete=round(total_frete, 2),
            custo_total_servico=round(total_servico, 2),
            custo_total_deslocamento=round(total_desloc, 2),
            total_geral=round(total_materiais + total_km + total_pedagio + total_frete + total_servico + total_desloc, 2),
            detalhes_por_visita=detalhes_por_visita,
            detalhes_materiais_compilado=detalhes_materiais,
            valores_utilizados=dict(self.valores),
        )

    def calcular_para_chamado(self, chamado) -> CustoTotalResponse:
        return self.calcular_custo_chamado(self.chamado_para_dict(chamado))


# ---------------------------------------------------------------------------------------------------------------------
# Snapshot (custo_os)
# ---------------------------------------------------------------------------------------------------------------------

def congelar_custo(db: Session, chamado, valores: Optional[Dict[str, float]] = None) -> CustoTotalResponse:
    """
    Calcula o custo e grava/atualiza o snapshot em `custo_os` (sem commit: entra na transação de quem chama). Chamar
    APÓS aplicar à sessão os dados finais. Sem `valores`, usa os globais vigentes (finalização); com `valores`, usa
    exatamente esses (recálculo após correção de materiais: reaproveita os valores congelados, RN-33 / RN-49).
    """
    from app.models.custo_os import CustoOS

    servico = CustoService(valores=valores, db=db)
    custo = servico.calcular_para_chamado(chamado)
    agora = datetime.now(timezone.utc)
    detalhes = custo.model_dump(mode="json", exclude={"congelado", "calculado_em", "valores_utilizados"})
    snapshot = db.get(CustoOS, chamado.id_os)
    if snapshot is None:
        snapshot = CustoOS(id_os=chamado.id_os)
        db.add(snapshot)
    snapshot.total = Decimal(str(custo.total_geral))
    snapshot.detalhes = detalhes
    snapshot.valores_utilizados = dict(servico.valores)
    snapshot.calculado_em = agora
    custo.congelado = True
    custo.calculado_em = agora
    return custo


def recalcular_custo_finalizado(db: Session, chamado) -> Tuple[Optional[float], CustoTotalResponse]:
    """
    RN-49 (v0.5): recalcula o custo de OS FINALIZADA após a correção de materiais pelo administrador.
    Usa os `valores_utilizados` JÁ CONGELADOS no snapshot (não a configuração global atual), de modo que mudanças
    posteriores na configuração não alterem o histórico (RN-33); substitui total/detalhes/calculado_em do snapshot.
    Retorna `(total_anterior, custo_novo)`; sem commit (entra na transação de quem chama). Chamar APÓS aplicar os
    materiais corrigidos à sessão (e `db.refresh(chamado)`).
    """
    from app.models.custo_os import CustoOS

    snapshot = db.get(CustoOS, chamado.id_os)
    anterior = float(snapshot.total) if snapshot is not None else None
    valores = None
    if snapshot is not None and isinstance(snapshot.valores_utilizados, dict):
        if all(k in snapshot.valores_utilizados for k in _CHAVES_CONFIG):
            valores = {k: float(snapshot.valores_utilizados[k]) for k in _CHAVES_CONFIG}
    return anterior, congelar_custo(db, chamado, valores=valores)


def obter_custo_da_os(db: Session, chamado) -> CustoTotalResponse:
    """
    `GET /custos`: OS Finalizada com snapshot -> devolve o snapshot imutável (CA-19). Demais casos -> cálculo atual
    com os valores globais vigentes. OS Finalizada legada sem snapshot é calculada ao vivo (e marcada como não congelada).
    """
    status = chamado.status.value if hasattr(chamado.status, "value") else str(chamado.status)
    if status == "Finalizado":
        try:
            from app.models.custo_os import CustoOS
            snapshot = db.get(CustoOS, chamado.id_os)
        except Exception:
            snapshot = None
        if snapshot is not None:
            resposta = CustoTotalResponse(**snapshot.detalhes)
            resposta.congelado = True
            resposta.calculado_em = snapshot.calculado_em
            resposta.valores_utilizados = snapshot.valores_utilizados
            return resposta
        logger.warning("OS %s Finalizada sem snapshot em custo_os; calculando ao vivo.", chamado.id_os)
    return CustoService(db=db).calcular_para_chamado(chamado)
