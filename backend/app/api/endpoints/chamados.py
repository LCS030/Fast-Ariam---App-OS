# app/api/endpoints/chamados.py
from fastapi import APIRouter, Depends, HTTPException, Query, Response, File, UploadFile, Form, Body
from typing import List, Optional, Any, Dict
from datetime import date, datetime
import base64
import uuid
import os
from app.models.material import Material
from sqlalchemy.orm import Session
from app.schemas.deslocamento import IniciarDeslocamentoPayload


from app.core.security import get_current_active_user, require_admin_role, require_technician_role
from app.db.database import get_db
from app.repositories.mysql_repository import SQLRepository
from app.repositories.in_memory_repository import deep_update
from app.schemas.chamado import Chamado, ChamadoCreate, ChamadoUpdate, StatusChamado
from app.schemas.visita import Visita, VisitaCreate, VisitaUpdate
from app.schemas.custo import CustoTotalResponse
from app.services.custo_service import CustoService
from app.services.file_service import save_upload_file

router = APIRouter()

# arquivos que podem ser listas (vários uploads)
MULTI_FILE_FIELDS = ["comprovante_pedagio_urls", "comprovante_frete_urls"]

ASSINATURA_DIR = "static/assinaturas"

if not os.path.exists(ASSINATURA_DIR):
    os.makedirs(ASSINATURA_DIR)

# campos de arquivo single — estendidos para cobrir fotos de ida/volta e odometro/assinatura
SINGLE_FILE_FIELDS = [
    "odometro_inicio_url",
    "odometro_fim_url",
    "assinatura_cliente_url",
    "foto_inicio_ida_url",
    "foto_fim_ida_url",
    "foto_inicio_volta_url",
    "foto_fim_volta_url",
]

def get_chamado_repository(db: Session = Depends(get_db)):
    return SQLRepository(db=db)

def get_cliente_repository(db: Session = Depends(get_db)):
    return SQLRepository(db=db)

def get_tecnico_repository(db: Session = Depends(get_db)):
    return SQLRepository(db=db)

def servico_to_dict(servico):
    return {
        "id_servico": servico.id_servico,
        "numero_serie_atendido": servico.numero_serie_atendido,
        "nome_equipamento": servico.nome_equipamento,
        "defeitos_principais": servico.defeitos_principais,
        "defeito_outros_descricao": servico.defeito_outros_descricao,
        "sub_defeitos_refrigeracao": servico.sub_defeitos_refrigeracao,
        "sub_defeitos_compressor": servico.sub_defeitos_compressor,
        "sub_defeitos_vazamento": servico.sub_defeitos_vazamento,
        "vazamento_ponto_descricao": servico.vazamento_ponto_descricao,
        "sub_defeitos_outros": servico.sub_defeitos_outros,
        "sub_defeitos_iluminacao": servico.sub_defeitos_iluminacao,
        "sub_defeitos_estrutura": servico.sub_defeitos_estrutura,
        "materiais_utilizados": [
            {
                "id_material": m.id_material,
                "nome": m.nome,
                "quantidade": m.quantidade,
                "valor": float(m.valor),
            }
            for m in servico.materiais_utilizados
        ],
    }


# ----------------------------
# Chamados (mantive sua lógica)
# ----------------------------
@router.post("/", response_model=Chamado, status_code=201)
def create_chamado(
    chamado_in: ChamadoCreate,
    repo: SQLRepository = Depends(get_chamado_repository),
    cliente_repo: SQLRepository = Depends(get_cliente_repository),
    _admin_user: dict = Depends(require_admin_role)
):
    cliente_db = cliente_repo.get_cliente_by_id(chamado_in.id_cliente)
    if not cliente_db or not cliente_db.is_active:
        raise HTTPException(status_code=404, detail=f"Cliente com id {chamado_in.id_cliente} não encontrado ou inativo.")

    chamado_data = chamado_in.model_dump()
    chamado_data['data_abertura'] = date.today()
    chamado_data['is_cancelled'] = False

    if chamado_data.get('id_tecnico_atribuido') is not None:
        chamado_data['status'] = StatusChamado.AGENDADO
    else:
        chamado_data['status'] = StatusChamado.ABERTO

    chamado_criado_db = repo.create_chamado(chamado_data)
    return chamado_criado_db


@router.get("/", response_model=List[Chamado])
def get_todos_chamados(
    repo: SQLRepository = Depends(get_chamado_repository),
    is_cancelled: Optional[bool] = Query(None, description="Filtra chamados pelo status de cancelamento"),
    current_user: dict = Depends(get_current_active_user)
):
    chamados_list_db = repo.get_chamados()
    response_list = []
    user_id = current_user.get("user_id")
    user_role = current_user.get("role")

    for chamado_db in chamados_list_db:
        if is_cancelled is not None and chamado_db.is_cancelled != is_cancelled:
            continue

        if user_role == "tecnico" and chamado_db.id_tecnico_atribuido != user_id:
            continue

        cliente = repo.get_cliente_by_id(chamado_db.id_cliente)
        cliente_nome = cliente.razao_social if cliente else None

        chamado_dict = Chamado.model_validate(chamado_db).model_dump()
        chamado_dict["cliente_nome"] = cliente_nome
        response_list.append(chamado_dict)

    return response_list

@router.get("/{chamado_id}", response_model=Chamado)
def get_chamado_por_id(
    chamado_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(get_current_active_user)
):
    chamado_db = repo.get_chamado_by_id(chamado_id)
    if not chamado_db or chamado_db.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")

    # Permissão: técnico só acessa seus próprios chamados
    user_id = current_user.get("user_id")
    role = current_user.get("role")
    if role == "tecnico" and chamado_db.id_tecnico_atribuido != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este chamado.")

    # pega o cliente
    cliente = repo.get_cliente_by_id(chamado_db.id_cliente)
    cliente_nome = cliente.razao_social if cliente else None

    chamado_dict = Chamado.model_validate(chamado_db).model_dump()
    chamado_dict["cliente_nome"] = cliente_nome

    return chamado_dict

@router.patch("/{chamado_id}", response_model=Chamado)
def update_chamado(
    chamado_id: int,
    chamado_in: ChamadoUpdate,
    repo: SQLRepository = Depends(get_chamado_repository),
    tecnico_repo: SQLRepository = Depends(get_tecnico_repository),
    current_user: dict = Depends(get_current_active_user),
):
    update_data = chamado_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")

    user_id = current_user.get("user_id")
    user_role = current_user.get("role")

    if user_role == "tecnico":
        chamado_db = repo.get_chamado_by_id(chamado_id)
        if not chamado_db or chamado_db.id_tecnico_atribuido != user_id:
            raise HTTPException(status_code=403, detail="Acesso negado a este chamado.")

        allowed_fields = {"status"}
        for field in update_data.keys():
            if field not in allowed_fields:
                raise HTTPException(status_code=403, detail=f"Técnicos não podem atualizar o campo '{field}'.")

    if user_role == "admin":
        if 'id_tecnico_atribuido' in update_data:
            novo_tecnico_id = update_data['id_tecnico_atribuido']
            if novo_tecnico_id is not None:
                tecnico_db = tecnico_repo.get_tecnico_by_id(novo_tecnico_id)
                if not tecnico_db or not tecnico_db.is_active:
                    raise HTTPException(status_code=404, detail=f"Técnico com id {novo_tecnico_id} não encontrado ou inativo.")
                if 'status' not in update_data:
                    update_data['status'] = StatusChamado.AGENDADO

    novo_status = update_data.get("status")
    if novo_status:
        if novo_status == StatusChamado.FINALIZADO:
            if user_role != "admin":
                raise HTTPException(status_code=403, detail="Técnicos devem finalizar o chamado através da atualização da visita.")
            update_data['data_conclusao'] = date.today()
        elif novo_status != StatusChamado.FINALIZADO:
            update_data['data_conclusao'] = None

    updated_chamado = repo.update_chamado(chamado_id, update_data)
    if updated_chamado is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    return updated_chamado


@router.delete("/{chamado_id}", status_code=204)
def delete_chamado(
    chamado_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    _admin_user: dict = Depends(require_admin_role)
):
    success = repo.delete_chamado(chamado_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")
    return Response(status_code=204)


# ----------------------------
# Visitas (create / update / upload)
# ----------------------------
@router.post("/{chamado_id}/visitas", response_model=Visita, status_code=201)
def add_visita_ao_chamado(
    chamado_id: int,
    visita_in: VisitaCreate,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(get_current_active_user),
):
    logged_user_id = current_user["user_id"]
    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")

    if chamado.id_tecnico_atribuido != logged_user_id:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Você não tem permissão para adicionar uma visita neste chamado.")

    if visita_in.servico_finalizado:
        raise HTTPException(status_code=400, detail="Não é possível criar uma visita já finalizada. Crie a visita, faça os uploads e depois finalize-a.")

    visita_data = visita_in.model_dump()
    visita_db = repo.create_visita(chamado_id, visita_data)

    dados_update_chamado = {}
    if visita_in.pendencia:
        dados_update_chamado['status'] = StatusChamado.PENDENTE
    elif chamado.status == StatusChamado.AGENDADO:
        dados_update_chamado['status'] = StatusChamado.EM_ATENDIMENTO

    if dados_update_chamado:
        repo.update_chamado(chamado_id, dados_update_chamado)

    return visita_db


@router.patch("/{chamado_id}/visitas/{visita_id}", response_model=Visita)
def update_visita_em_chamado(
    chamado_id: int,
    visita_id: int,
    visita_in: VisitaUpdate,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(get_current_active_user)
):
    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado ou cancelado")

    logged_user_id = current_user.get("user_id")
    user_role = current_user.get("role")
    if user_role == "tecnico" and chamado.id_tecnico_atribuido != logged_user_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para editar visitas deste chamado.")

    visita_db = repo.get_visita_by_id(visita_id)
    if not visita_db or visita_db.id_os != chamado_id:
        raise HTTPException(status_code=404, detail=f"Visita com ID {visita_id} não encontrada neste chamado.")

    update_data = visita_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")

    visita_atualizada_dict = deep_update(visita_db.__dict__, update_data)

    if visita_atualizada_dict.get('servico_finalizado') is True:
        if not visita_atualizada_dict.get('assinatura_cliente_url'):
            raise HTTPException(status_code=400, detail="Assinatura do cliente é obrigatória para finalizar a visita.")

        if visita_atualizada_dict.get('km_total', 0) > 0:
            if not visita_atualizada_dict.get('odometro_inicio_url') or not visita_atualizada_dict.get('odometro_fim_url'):
                raise HTTPException(status_code=400, detail="Fotos do odômetro de início e fim são obrigatórias se km_total > 0.")

        if visita_atualizada_dict.get('valor_pedagio', 0.0) > 0:
            if not visita_atualizada_dict.get('comprovante_pedagio_urls'):
                raise HTTPException(status_code=400, detail="Comprovante(s) de pedágio são obrigatórios se valor_pedagio > 0.")

        if visita_atualizada_dict.get('valor_frete_devolucao', 0.0) > 0:
            if not visita_atualizada_dict.get('comprovante_frete_urls'):
                raise HTTPException(status_code=400, detail="Comprovante(s) de frete são obrigatórios se valor_frete_devolucao > 0.")

        repo.update_chamado(chamado_id, {"status": StatusChamado.FINALIZADO, "data_conclusao": date.today()})

    elif visita_atualizada_dict.get('servico_finalizado') is False:
        pendencia = visita_atualizada_dict.get('pendencia')
        repo.update_chamado(chamado_id, {
            "status": StatusChamado.PENDENTE if pendencia else StatusChamado.EM_ATENDIMENTO,
            "data_conclusao": None
        })

    updated_visita = repo.update_visita(visita_id, update_data)
    if updated_visita is None:
        raise HTTPException(status_code=404, detail="Erro ao atualizar visita.")

    return updated_visita


# ----------------------------
# Custos (mantive)
# ----------------------------
@router.post("/{chamado_id}/iniciar-atendimento", response_model=Chamado)
def tecnico_inicia_atendimento(
    chamado_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
):
    logged_user_id = current_user.get("user_id")
    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado ou cancelado")

    if chamado.id_tecnico_atribuido != logged_user_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para iniciar este chamado.")

    if chamado.status not in [StatusChamado.AGENDADO, StatusChamado.PENDENTE]:
        raise HTTPException(status_code=400, detail=f"Não é possível iniciar um chamado com status '{chamado.status}'")

    update_data = {"status": StatusChamado.EM_ATENDIMENTO}
    updated_chamado = repo.update_chamado(chamado_id, update_data)
    return updated_chamado


@router.get("/{chamado_id}/custos", response_model=CustoTotalResponse)
def get_custos_do_chamado(
    chamado_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(get_current_active_user)
):
    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado ou cancelado.")

    user_id = current_user.get("user_id")
    user_role = current_user.get("role")
    if user_role == "tecnico" and chamado.id_tecnico_atribuido != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado aos custos deste chamado.")

    service = CustoService()
    chamado_dict = Chamado.model_validate(chamado).model_dump()
    custos = service.calcular_custo_chamado(chamado_dict)
    return custos


# ----------------------------
# Upload generic de visita (mantive)
# ----------------------------
@router.post("/{chamado_id}/visitas/{visita_id}/upload_file", response_model=Visita)
def upload_file_visita(
    chamado_id: int,
    visita_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(get_current_active_user),
    file: UploadFile = File(...),
    file_type: str = Form(..., description="Campo da visita para ser atualizado (URL do arquivo)."),
):
    logged_user_id = current_user.get("user_id")
    user_role = current_user.get("role")
    chamado = repo.get_chamado_by_id(chamado_id)

    if not chamado or chamado.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado ou cancelado.")

    if user_role == "tecnico" and chamado.id_tecnico_atribuido != logged_user_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para este chamado.")

    visita_db = repo.get_visita_by_id(visita_id)
    if not visita_db or visita_db.id_os != chamado_id:
        raise HTTPException(status_code=404, detail=f"Visita com ID {visita_id} não encontrada.")

    valid_fields = SINGLE_FILE_FIELDS + MULTI_FILE_FIELDS
    if file_type not in valid_fields:
        raise HTTPException(status_code=400, detail=f"Tipo de arquivo inválido: '{file_type}'.")

    prefixo_nome_arquivo = f"chamado_{chamado_id}_visita_{visita_id}_{file_type}"
    file_url = save_upload_file(file, prefixo_nome_arquivo)

    visita_para_atualizar = {}
    if file_type in SINGLE_FILE_FIELDS:
        visita_para_atualizar[file_type] = file_url
    elif file_type in MULTI_FILE_FIELDS:
        current_list = getattr(visita_db, file_type) or []
        if not isinstance(current_list, list): current_list = []
        current_list.append(file_url)
        visita_para_atualizar[file_type] = current_list

    visita_atualizada = repo.update_visita(visita_id, visita_para_atualizar)
    return visita_atualizada


# ----------------------------
# Novos endpoints: deslocamento (ida/volta)
# ----------------------------
@router.post("/{chamado_id}/visitas/{visita_id}/iniciar-atendimento")
def iniciar_atendimento(
    chamado_id: int,
    visita_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
):
    visita = repo.get_visita_by_id(visita_id)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")

    logged_user_id = current_user.get("user_id")
    if chamado.id_tecnico_atribuido != logged_user_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão.")

    # Não deixa iniciar antes de finalizar deslocamento de ida
    if not visita.hora_fim_ida:
      raise HTTPException(status_code=400, detail="Finalize o deslocamento de ida antes de iniciar o atendimento.")

    # Evita duplas execuções
    if visita.hora_inicio_atendimento:
        raise HTTPException(status_code=400, detail="Atendimento já iniciado.")

    now_time = datetime.now().strftime("%H:%M")

    update = {
        "hora_inicio_atendimento": now_time
    }

    visita_editada = repo.update_visita(visita_id, update)

    # Deixa o chamado como em atendimento
    repo.update_chamado(chamado_id, {"status": StatusChamado.EM_ATENDIMENTO})

    return visita_editada



@router.post("/{chamado_id}/visitas/{visita_id}/finalizar-deslocamento")
def finalizar_deslocamento(
    chamado_id: int,
    visita_id: int,
    payload: Dict[str, Any] = Body(...),
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
):
    tipo = payload.get("tipo")
    km_fim = payload.get("km_fim")

    if tipo not in ["ida", "volta"]:
        raise HTTPException(status_code=400, detail="tipo deve ser 'ida' ou 'volta'")

    visita = repo.get_visita_by_id(visita_id)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")
    logged_user_id = current_user.get("user_id")
    if current_user.get("role") == "tecnico" and chamado.id_tecnico_atribuido != logged_user_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para este chamado.")

    now_time = datetime.now().strftime("%H:%M")

    if tipo == "ida":
        if not getattr(visita, "hora_inicio_ida", None):
            raise HTTPException(status_code=400, detail="Deslocamento de ida não foi iniciado")
        if getattr(visita, "hora_fim_ida", None):
            raise HTTPException(status_code=400, detail="Deslocamento de ida já foi finalizado")

        update = {
            "km_fim_ida": km_fim,
            "hora_fim_ida": now_time
        }
    else:  # volta
        if not getattr(visita, "hora_inicio_volta", None):
            raise HTTPException(status_code=400, detail="Deslocamento de volta não foi iniciado")
        if getattr(visita, "hora_fim_volta", None):
            raise HTTPException(status_code=400, detail="Deslocamento de volta já foi finalizado")

        update = {
            "km_fim_volta": km_fim,
            "hora_fim_volta": now_time
        }

    # se finalizou deslocamento de volta e visita.servico_finalizado for True, marca chamado como finalizado
    visita_editada = repo.update_visita(visita_id, update)

    if tipo == "volta":
        # se a visita já estiver finalizada (servico_finalizado True), encerramos a OS
        if getattr(visita_editada, "servico_finalizado", False):
            repo.update_chamado(chamado_id, {"status": StatusChamado.FINALIZADO, "data_conclusao": date.today()})

    return visita_editada


@router.post("/{chamado_id}/visitas/{visita_id}/upload-deslocamento", response_model=Visita)
def upload_foto_deslocamento(
    chamado_id: int,
    visita_id: int,
    file: UploadFile = File(...),
    tipo: str = Form(...),       # "ida" | "volta"
    momento: str = Form(...),    # "inicio" | "fim"
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(get_current_active_user),
):
    if tipo not in ["ida", "volta"]:
        raise HTTPException(status_code=400, detail="tipo inválido")
    if momento not in ["inicio", "fim"]:
        raise HTTPException(status_code=400, detail="momento inválido")

    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado ou cancelado.")

    logged_user_id = current_user.get("user_id")
    user_role = current_user.get("role")
    if user_role == "tecnico" and chamado.id_tecnico_atribuido != logged_user_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para este chamado.")

    visita_db = repo.get_visita_by_id(visita_id)
    if not visita_db or visita_db.id_os != chamado_id:
        raise HTTPException(status_code=404, detail=f"Visita com ID {visita_id} não encontrada.")

    prefix = f"visita_{visita_id}_{tipo}_{momento}"
    file_url = save_upload_file(file, prefix)

    field = f"foto_{momento}_{tipo}_url"  # ex: foto_inicio_ida_url
    update = {field: file_url}
    updated = repo.update_visita(visita_id, update)
    return updated


@router.get("/{chamado_id}/visitas/{visita_id}/estado")
def estado_visita(
    chamado_id: int,
    visita_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(get_current_active_user),
):
    visita = repo.get_visita_by_id(visita_id)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    # Função auxiliar para normalizar o valor
    def clean(v):
        return None if v in (None, "", " ", "  ") else v

    # NORMALIZAÇÃO DOS CAMPOS QUE PODEM VIR ""
    hora_inicio_ida = clean(getattr(visita, "hora_inicio_ida", None))
    hora_fim_ida = clean(getattr(visita, "hora_fim_ida", None))

    hora_inicio_atendimento = clean(getattr(visita, "hora_inicio_atendimento", None))
    hora_fim_atendimento = clean(getattr(visita, "hora_fim_atendimento", None))

    hora_inicio_volta = clean(getattr(visita, "hora_inicio_volta", None))
    hora_fim_volta = clean(getattr(visita, "hora_fim_volta", None))

    # ------------------------
    # REGRAS DO FLUXO OFICIAL
    # ------------------------
    estado = {
        # 1) Ida
        "pode_iniciar_deslocamento_ida": hora_inicio_ida is None,
        "pode_finalizar_deslocamento_ida": hora_inicio_ida is not None and hora_fim_ida is None,

        # 2) Atendimento
        "pode_iniciar_atendimento": hora_fim_ida is not None and hora_inicio_atendimento is None,
        "pode_finalizar_atendimento": hora_inicio_atendimento is not None and hora_fim_atendimento is None,

        # 3) Volta
        "pode_iniciar_deslocamento_volta": hora_fim_atendimento is not None and hora_inicio_volta is None,
        "pode_finalizar_deslocamento_volta": hora_inicio_volta is not None and hora_fim_volta is None,

        # 4) Conclusão final
        "pode_concluir_chamado": hora_fim_volta is not None,
    }

    return estado

@router.post("/{chamado_id}/visitas/{visita_id}/iniciar-atendimento")
def iniciar_atendimento(
    chamado_id: int,
    visita_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
):
    visita = repo.get_visita_by_id(visita_id)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")

    if chamado.id_tecnico_atribuido != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Você não tem permissão para este chamado")

    # Regras
    if not visita.hora_fim_ida:
        raise HTTPException(status_code=400, detail="Finalize o deslocamento de ida antes de iniciar o atendimento.")

    if visita.hora_inicio_atendimento:
        raise HTTPException(status_code=400, detail="O atendimento já foi iniciado")

    now_time = datetime.now().strftime("%H:%M")

    update = {
        "hora_inicio_atendimento": now_time
    }

    visita_editada = repo.update_visita(visita_id, update)

    # Chamado passa a EM_ATENDIMENTO
    repo.update_chamado(chamado_id, {"status": StatusChamado.EM_ATENDIMENTO})

    return visita_editada


@router.post("/{chamado_id}/visitas/{visita_id}/iniciar-atendimento")
def iniciar_atendimento_visita(
    chamado_id: int,
    visita_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
):
    # Verifica o chamado
    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado ou cancelado")

    # Permissão
    logged_user_id = current_user.get("user_id")
    if chamado.id_tecnico_atribuido != logged_user_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para este chamado.")

    # Verifica a visita
    visita = repo.get_visita_by_id(visita_id)
    if not visita or visita.id_os != chamado_id:
        raise HTTPException(status_code=404, detail="Visita não encontrada neste chamado")

    # Já iniciou?
    if getattr(visita, "hora_inicio_atendimento", None):
        raise HTTPException(status_code=400, detail="Atendimento já foi iniciado.")

    # Define hora atual HH:mm
    now = datetime.now().strftime("%H:%M")

    update = {
        "hora_inicio_atendimento": now
    }

    visita_atualizada = repo.update_visita(visita_id, update)

    # Atualiza status do chamado
    repo.update_chamado(chamado_id, {"status": StatusChamado.EM_ATENDIMENTO})

    return visita_atualizada

@router.get("/{chamado_id}/visitas/{visita_id}/servicos")
def listar_servicos_equipamento(chamado_id: int, visita_id: int,
                                repo: SQLRepository = Depends(get_chamado_repository),
                                current_user: dict = Depends(get_current_active_user)):

    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(404, "Chamado não encontrado ou cancelado.")

    if current_user["role"] == "tecnico" and chamado.id_tecnico_atribuido != current_user["user_id"]:
        raise HTTPException(403, "Acesso negado.")

    visita = repo.get_visita_by_id(visita_id)
    if not visita or visita.id_os != chamado_id:
        raise HTTPException(404, "Visita não encontrada neste chamado.")

    servicos = repo.get_servicos_by_visita(visita_id)
    return [servico_to_dict(s) for s in servicos]

@router.post("/{chamado_id}/visitas/{visita_id}/servicos")
def criar_servico_equipamento(chamado_id: int, visita_id: int,
                              payload: Dict[str, Any] = Body(...),
                              repo: SQLRepository = Depends(get_chamado_repository),
                              current_user: dict = Depends(require_technician_role)):

    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(404, "Chamado não encontrado ou cancelado.")

    if chamado.id_tecnico_atribuido != current_user["user_id"]:
        raise HTTPException(403, "Você não tem permissão.")

    visita = repo.get_visita_by_id(visita_id)
    if not visita or visita.id_os != chamado_id:
        raise HTTPException(404, "Visita não encontrada neste chamado.")

    materiais = payload.pop("materiais_utilizados", [])

    servico = repo.create_servico_equipamento(visita_id, payload)

    for m in materiais:
        repo.db.add(Material(
            id_servico=servico.id_servico,
            nome=m["nome"],
            quantidade=m["quantidade"],
            valor=m["valor"]
        ))

    repo.db.commit()

    return servico_to_dict(servico)


@router.patch("/{chamado_id}/visitas/{visita_id}/servicos/{servico_id}")
def atualizar_servico_equipamento(chamado_id: int, visita_id: int, servico_id: int,
                                  payload: Dict[str, Any] = Body(...),
                                  repo: SQLRepository = Depends(get_chamado_repository),
                                  current_user: dict = Depends(require_technician_role)):

    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(404, "Chamado não encontrado.")

    if chamado.id_tecnico_atribuido != current_user["user_id"]:
        raise HTTPException(403, "Você não tem permissão.")

    visita = repo.get_visita_by_id(visita_id)
    if not visita or visita.id_os != chamado_id:
        raise HTTPException(404, "Visita não encontrada neste chamado.")

    materiais = payload.pop("materiais_utilizados", None)

    servico_atualizado = repo.update_servico_equipamento(servico_id, payload)
    if not servico_atualizado:
        raise HTTPException(404, "Serviço não encontrado.")

    if materiais is not None:
        repo.db.query(Material).filter(Material.id_servico == servico_id).delete()

        for m in materiais:
            repo.db.add(Material(
                id_servico=servico_id,
                nome=m["nome"],
                quantidade=m["quantidade"],
                valor=m["valor"]
            ))

        repo.db.commit()

    repo.db.commit()

    return servico_to_dict(servico_atualizado)

@router.patch("/{chamado_id}/visitas/{visita_id}", response_model=Visita)
def atualizar_visita(
    chamado_id: int,
    visita_id: int,
    data: Dict[str, Any],
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role),
):
    visita = repo.get_visita_by_id(visita_id)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    updated = repo.update_visita(visita_id, data)
    return updated


@router.post("/{chamado_id}/visitas/{visita_id}/finalizar-dados")
def salvar_dados_cliente(
    chamado_id: int,
    visita_id: int,
    payload: Dict[str, str] = Body(...),
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
):
    visita = repo.get_visita_by_id(visita_id)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    nome = payload.get("nome_cliente")
    documento = payload.get("documento_cliente")

    if not nome or not documento:
        raise HTTPException(status_code=400, detail="Nome e documento são obrigatórios.")

    update = {
        "nome_cliente": nome,
        "documento_cliente": documento
    }

    repo.update_visita(visita_id, update)

    return {"message": "Dados registrados com sucesso"}

@router.post("/{chamado_id}/visitas/{visita_id}/finalizar-atendimento")
def finalizar_atendimento(
    chamado_id: int,
    visita_id: int,
    payload: dict = Body(...),
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
):

    nome_cliente = payload.get("nome_cliente")
    documento_cliente = payload.get("documento_cliente")
    assinatura_base64 = payload.get("assinatura_base64")

    if not nome_cliente or not documento_cliente or not assinatura_base64:
        raise HTTPException(status_code=400, detail="Campos obrigatórios faltando.")

    visita = repo.get_visita_by_id(visita_id)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    # ---- DECODIFICA BASE64 ----
    if assinatura_base64.startswith("data:image"):
        assinatura_base64 = assinatura_base64.split(",")[1]

    img_bytes = base64.b64decode(assinatura_base64)

    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(ASSINATURA_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(img_bytes)

    assinatura_url = f"/static/assinaturas/{filename}"

    # ---- ATUALIZA A VISITA ----
    update_data = {
        "assinatura_cliente_url": assinatura_url,
        "nome_cliente": nome_cliente,
        "documento_cliente": documento_cliente,
        "hora_fim_atendimento": datetime.now().strftime("%H:%M"),
        "servico_finalizado": True
    }

    repo.update_visita(visita_id, update_data)

    # ---- FINALIZA O CHAMADO ----
    repo.update_chamado(chamado_id, {
        "status": StatusChamado.FINALIZADO,
        "data_conclusao": date.today(),
        "is_completed": True  # <--- AQUI TUDO JUNTO
    })

    repo.db.commit()

    return {
        "status": "ok",
        "assinatura_url": assinatura_url
    }


@router.post("/{chamado_id}/visitas/{visita_id}/iniciar-deslocamento")
def iniciar_deslocamento(
    chamado_id: int,
    visita_id: int,
    payload: IniciarDeslocamentoPayload, 
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
    
):
    tipo = payload.tipo
    km_inicio = payload.km_inicio

    

    if tipo not in ["ida", "volta"]:
        raise HTTPException(status_code=400, detail="tipo deve ser 'ida' ou 'volta'")

    if km_inicio is None:
        raise HTTPException(status_code=400, detail="km_inicio é obrigatório")

    # --- validar chamado ---
    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado or chamado.is_cancelled:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")

    if chamado.id_tecnico_atribuido != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Você não tem permissão")

    # --- validar visita ---
    visita = repo.get_visita_by_id(visita_id)
    if not visita or visita.id_os != chamado_id:
        raise HTTPException(status_code=404, detail="Visita não encontrada no chamado")

    now_time = datetime.now().strftime("%H:%M")

    # ---------------------------
    # INÍCIO DO DESLOCAMENTO IDA
    # ---------------------------
    if tipo == "ida":
        # já iniciado antes?
        if getattr(visita, "hora_inicio_ida", None):
            raise HTTPException(status_code=400, detail="Deslocamento de ida já iniciado")

        update = {
            "km_inicio_ida": km_inicio,
            "hora_inicio_ida": now_time
        }

    # ---------------------------
    # INÍCIO DO DESLOCAMENTO VOLTA
    # ---------------------------
    if tipo == "volta":
        # só pode iniciar volta após atendimento finalizado
        if not getattr(visita, "hora_fim_atendimento", None):
            raise HTTPException(
                status_code=400,
                detail="Finalize o atendimento antes de iniciar o deslocamento de volta"
            )

        if getattr(visita, "hora_inicio_volta", None):
            raise HTTPException(status_code=400, detail="Deslocamento de volta já iniciado")

        update = {
            "km_inicio_volta": km_inicio,
            "hora_inicio_volta": now_time
        }

    # atualizar visita
    visita_editada = repo.update_visita(visita_id, update)
    repo.db.commit()

    return {
        "message": "Deslocamento iniciado com sucesso",
        "tipo": tipo,
        "km_inicio": km_inicio,
        "hora_inicio": now_time
    }

@router.post("/{chamado_id}/concluir")
def concluir_chamado(
    chamado_id: int,
    repo: SQLRepository = Depends(get_chamado_repository),
    current_user: dict = Depends(require_technician_role)
):
    chamado = repo.get_chamado_by_id(chamado_id)
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")

    if chamado.id_tecnico_atribuido != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Você não tem permissão")

    # Marca como finalizado
    repo.update_chamado(chamado_id, {
        "is_completed": True,
        "data_conclusao": date.today()
    })

    repo.db.commit()

    return {"status": "ok", "message": "Chamado concluído com sucesso"}
