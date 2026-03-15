from datetime import datetime
from typing import Dict, Any
from app.core.config import VALORES_ASSISTENCIA
from app.schemas.custo import CustoTotalResponse, CustoVisitaDetalhado, CustoMaterialDetalhado


def _parse_duration_in_hours(start_time_str: str, end_time_str: str) -> float:
    """ Calcula a duração entre duas strings de hora em horas decimais."""
    try:
        t_start = datetime.strptime(start_time_str, '%H:%M')
        t_end = datetime.strptime(end_time_str, '%H:%M')
        duration = t_end - t_start
        return duration.total_seconds() / 3600
    except ValueError:
        return 0.0


class CustoService:
    def __init__(self, valores_assistencia: Dict = VALORES_ASSISTENCIA):
        self.regras = valores_assistencia

    def calcular_custo_chamado(self, chamado: Dict[str, Any]) -> CustoTotalResponse:
        total_geral = 0.0
        custo_total_materiais = 0.0
        custo_total_km = 0.0
        custo_total_pedagio = 0.0
        custo_total_frete = 0.0
        custo_total_servico = 0.0
        custo_total_deslocamento = 0.0

        detalhes_por_visita = []
        materiais_compilado = {}

        for visita in chamado.get('visitas', []):
            custo_visita_materiais = 0.0
            for servico in visita.get('servicos_realizados', []):
                for material in servico.get('materiais_utilizados', []):
                    qnt, val = material.get('quantidade', 0), material.get('valor', 0)
                    subtotal_mat = round(qnt * val, 2)
                    custo_visita_materiais += subtotal_mat

                    nome_mat = material.get('nome', 'Desconhecido')
                    if nome_mat not in materiais_compilado:
                        materiais_compilado[nome_mat] = {'qnt': 0, 'val_unit': val, 'total': 0.0}
                    materiais_compilado[nome_mat]['qnt'] += qnt
                    materiais_compilado[nome_mat]['total'] += subtotal_mat

            custo_visita_materiais = round(custo_visita_materiais, 2)

            custo_visita_km = round(visita.get('km_total', 0) * self.regras['QUILOMETRAGEM'], 2)

            custo_visita_pedagio = round(visita.get('valor_pedagio', 0.0), 2)
            custo_visita_frete = round(visita.get('valor_frete_devolucao', 0.0), 2)

            horas_deslocamento = _parse_duration_in_hours(
                visita.get('hora_inicio_deslocamento', '00:00'),
                visita.get('hora_chegada_cliente', '00:00')
            )
            custo_visita_deslocamento = round(horas_deslocamento * self.regras['TEMPO_DESLOCAMENTO_TECNICO'], 2)

            horas_servico = _parse_duration_in_hours(
                visita.get('hora_inicio_atendimento', '00:00'),
                visita.get('hora_fim_atendimento', '00:00')
            )

            custo_visita_servico = 0.0
            if horas_servico > 0:
                if horas_servico <= 1:
                    custo_visita_servico = self.regras['PRIMEIRA_HORA_TECNICO']
                else:
                    custo_visita_servico = self.regras['PRIMEIRA_HORA_TECNICO'] + \
                                           ((horas_servico - 1) * self.regras['HORA_TECNICO'])

            custo_visita_servico = round(custo_visita_servico, 2)

            subtotal_visita = round((custo_visita_materiais + custo_visita_km + custo_visita_pedagio +
                                     custo_visita_frete + custo_visita_deslocamento + custo_visita_servico), 2)

            detalhes_por_visita.append(CustoVisitaDetalhado(
                id_visita=visita.get('id', 0),
                data=visita.get('data_visita', ''),
                custo_total_materiais=custo_visita_materiais,
                custo_km=custo_visita_km,
                custo_pedagio=custo_visita_pedagio,
                custo_frete=custo_visita_frete,
                custo_tempo_servico=custo_visita_servico,
                custo_tempo_deslocamento=custo_visita_deslocamento,
                subtotal_visita=subtotal_visita
            ))

            custo_total_materiais += custo_visita_materiais
            custo_total_km += custo_visita_km
            custo_total_pedagio += custo_visita_pedagio
            custo_total_frete += custo_visita_frete
            custo_total_servico += custo_visita_servico
            custo_total_deslocamento += custo_visita_deslocamento

        detalhes_materiais = [
            CustoMaterialDetalhado(
                nome=nome,
                quantidade=data['qnt'],
                valor_unitario=data['val_unit'],
                valor_total=round(data['total'], 2)
            ) for nome, data in materiais_compilado.items()
        ]

        return CustoTotalResponse(
            id_os=chamado.get('id', 0),
            custo_total_materiais=round(custo_total_materiais, 2),
            custo_total_km=round(custo_total_km, 2),
            custo_total_pedagio=round(custo_total_pedagio, 2),
            custo_total_frete=round(custo_total_frete, 2),
            custo_total_servico=round(custo_total_servico, 2),
            custo_total_deslocamento=round(custo_total_deslocamento, 2),
            total_geral=round(custo_total_materiais + custo_total_km + custo_total_pedagio +
                              custo_total_frete + custo_total_servico + custo_total_deslocamento, 2),
            detalhes_por_visita=detalhes_por_visita,
            detalhes_materiais_compilado=detalhes_materiais
        )