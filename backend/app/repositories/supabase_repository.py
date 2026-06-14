from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date
from app.models.tecnico import Tecnico
from app.models.cliente import Cliente
from app.models.chamado import OrdemServico
from app.models.visita import Visita
from app.models.servico_equipamento import ServicoEquipamento
from app.models.material import Material
from app.schemas.base_schemas import StatusChamado
from app.schemas.tecnico import TecnicoCreate, TecnicoUpdate
from app.schemas.cliente import ClienteCreate, ClienteUpdate
from app.schemas.chamado import ChamadoCreate, ChamadoUpdate
from app.schemas.visita import VisitaCreate, VisitaUpdate
from app.repositories.in_memory_repository import deep_update
from app.models.comprovante import Comprovante
from app.models.servico_defeito import ServicoDefeito
from app.models.servico_foto import ServicoFoto
from app.models.pausa import Pausa


class SQLRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_tecnico_by_id(self, tecnico_id: int) -> Optional[Tecnico]:
        return self.db.query(Tecnico).filter(Tecnico.id_tecnico == tecnico_id).first()

    def get_tecnico_by_email(self, email: str) -> Optional[Tecnico]:
        return self.db.query(Tecnico).filter(Tecnico.email == email).first()

    def get_tecnicos(self, is_active: Optional[bool] = None) -> list[type[Tecnico]]:
        query = self.db.query(Tecnico)
        if is_active is not None:
            query = query.filter(Tecnico.is_active == is_active)
        return query.all()

    def create_tecnico(self, tecnico_data: dict) -> Tecnico:
        dados_bancarios = tecnico_data.pop("dados_bancarios", {})
        if dados_bancarios:
            tecnico_data["banco"] = dados_bancarios.get("banco")
            tecnico_data["agencia"] = dados_bancarios.get("agencia")
            tecnico_data["conta"] = dados_bancarios.get("conta")
            tecnico_data["pix"] = dados_bancarios.get("pix")

        db_tecnico = Tecnico(**tecnico_data)
        self.db.add(db_tecnico)
        self.db.commit()
        self.db.refresh(db_tecnico)
        return db_tecnico

    def update_tecnico(self, tecnico_id: int, tecnico_in: TecnicoUpdate) -> Optional[Tecnico]:
        db_tecnico = self.get_tecnico_by_id(tecnico_id)
        if not db_tecnico:
            return None

        update_data = tecnico_in.model_dump(exclude_unset=True)
        dados_bancarios = update_data.pop("dados_bancarios", None)
        if dados_bancarios:
            if "banco" in dados_bancarios: db_tecnico.banco = dados_bancarios["banco"]
            if "agencia" in dados_bancarios: db_tecnico.agencia = dados_bancarios["agencia"]
            if "conta" in dados_bancarios: db_tecnico.conta = dados_bancarios["conta"]
            if "pix" in dados_bancarios: db_tecnico.pix = dados_bancarios["pix"]

        for key, value in update_data.items():
            if hasattr(db_tecnico, key):
                setattr(db_tecnico, key, value)

        self.db.commit()
        self.db.refresh(db_tecnico)
        return db_tecnico

    def delete_tecnico(self, tecnico_id: int) -> bool:
        db_tecnico = self.get_tecnico_by_id(tecnico_id)
        if not db_tecnico:
            return False

        db_tecnico.is_active = False
        self.db.commit()
        return True

    def get_cliente_by_id(self, cliente_id: int) -> Optional[Cliente]:
        return self.db.query(Cliente).filter(Cliente.id_cliente == cliente_id).first()

    def get_clientes(self, is_active: Optional[bool] = None) -> list[type[Cliente]]:
        query = self.db.query(Cliente)
        if is_active is not None:
            query = query.filter(Cliente.is_active == is_active)
        return query.all()

    def create_cliente(self, cliente_data: dict) -> Cliente:
        db_cliente = Cliente(**cliente_data)
        self.db.add(db_cliente)
        self.db.commit()
        self.db.refresh(db_cliente)
        return db_cliente

    def update_cliente(self, cliente_id: int, cliente_in: ClienteUpdate) -> Optional[Cliente]:
        db_cliente = self.get_cliente_by_id(cliente_id)
        if not db_cliente:
            return None
        update_data = cliente_in.model_dump(exclude_unset=True)
        db_cliente_dict = {}
        for cliente in db_cliente.__table__.columns:
            db_cliente_dict[cliente.name] = getattr(db_cliente, cliente.name)
        merged_data = deep_update(db_cliente_dict, update_data)
        for key, value in merged_data.items():
            if hasattr(db_cliente, key):
                setattr(db_cliente, key, value)
        self.db.add(db_cliente)
        self.db.commit()
        self.db.refresh(db_cliente)
        return db_cliente

    def delete_cliente(self, cliente_id: int) -> bool:
        db_cliente = self.get_cliente_by_id(cliente_id)
        if not db_cliente:
            return False
        db_cliente.is_active = False
        self.db.commit()
        return True

    def get_chamado_by_id(self, chamado_id: int) -> Optional[OrdemServico]:
        from sqlalchemy.orm import joinedload

        return self.db.query(OrdemServico).options(
            joinedload(OrdemServico.visitas)
            .joinedload(Visita.servicos_realizados)
            .joinedload(ServicoEquipamento.materiais_utilizados),
            joinedload(OrdemServico.cliente),
            joinedload(OrdemServico.tecnico)
        ).filter(OrdemServico.id_os == chamado_id).first()

    def get_chamados(self) -> list[type[OrdemServico]]:
        from sqlalchemy.orm import joinedload

        return self.db.query(OrdemServico).options(
            joinedload(OrdemServico.visitas)
            .joinedload(Visita.servicos_realizados)
            .joinedload(ServicoEquipamento.materiais_utilizados),
            joinedload(OrdemServico.cliente),
            joinedload(OrdemServico.tecnico)
        ).all()

    def create_chamado(self, chamado_data: dict) -> OrdemServico:
        db_chamado = OrdemServico(**chamado_data)
        self.db.add(db_chamado)
        self.db.commit()
        self.db.refresh(db_chamado)
        return db_chamado

    def update_chamado(self, chamado_id: int, update_data: dict) -> Optional[OrdemServico]:
        rows_updated = self.db.query(OrdemServico).filter(OrdemServico.id_os == chamado_id).update(update_data)
        if rows_updated == 0:
            return None
        self.db.commit()
        return self.get_chamado_by_id(chamado_id)

    def delete_chamado(self, chamado_id: int) -> bool:
        db_chamado = self.get_chamado_by_id(chamado_id)
        if not db_chamado:
            return False
        db_chamado.is_cancelled = True
        self.db.commit()
        return True

    def create_servico_equipamento(self, visita_id: int, servico_data: dict) -> ServicoEquipamento:
        materiais_data = servico_data.pop('materiais_utilizados', [])

        defeitos_mapping = {
            'principal': servico_data.pop('defeitos_principais', []),
            'refrigeracao': servico_data.pop('sub_defeitos_refrigeracao', []),
            'compressor': servico_data.pop('sub_defeitos_compressor', []),
            'vazamento': servico_data.pop('sub_defeitos_vazamento', []),
            'outros': servico_data.pop('sub_defeitos_outros', []),
            'iluminacao': servico_data.pop('sub_defeitos_iluminacao', []),
            'estrutura': servico_data.pop('sub_defeitos_estrutura', [])
        }

        # 🔥 A CORREÇÃO ESTÁ AQUI: Remove as propriedades somente leitura antes de instanciar!
        servico_data.pop('fotos_defeito', None)
        servico_data.pop('fotos_conserto', None)

        servico = ServicoEquipamento(**servico_data, id_visita=visita_id)

        for m in materiais_data:
            servico.materiais_utilizados.append(Material(**m))

        for tipo, lista in defeitos_mapping.items():
            for d in lista:
                servico.defeitos.append(ServicoDefeito(tipo=tipo, defeito=d))

        self.db.add(servico)
        self.db.commit()
        self.db.refresh(servico)
        return servico

    def update_servico_equipamento(self, servico_id: int, update_data: dict):
        materiais_data = update_data.pop('materiais_utilizados', None)

        # 🔥 A CORREÇÃO AQUI TAMBÉM:
        update_data.pop('fotos_defeito', None)
        update_data.pop('fotos_conserto', None)

        defeitos_keys = ['defeitos_principais', 'sub_defeitos_refrigeracao', 'sub_defeitos_compressor',
                         'sub_defeitos_vazamento', 'sub_defeitos_outros', 'sub_defeitos_iluminacao',
                         'sub_defeitos_estrutura']

        defeitos_updates = {}
        for key in defeitos_keys:
            if key in update_data:
                tipo = key.replace('sub_defeitos_', '').replace('defeitos_principais', 'principal')
                defeitos_updates[tipo] = update_data.pop(key)

        rows = self.db.query(ServicoEquipamento).filter(ServicoEquipamento.id_servico == servico_id).update(update_data)
        if rows == 0:
            return None

        if materiais_data is not None:
            self.db.query(Material).filter(Material.id_servico == servico_id).delete()
            for m in materiais_data:
                self.db.add(Material(id_servico=servico_id, **m))

        if defeitos_updates:
            for tipo, lista in defeitos_updates.items():
                self.db.query(ServicoDefeito).filter(ServicoDefeito.id_servico == servico_id,
                                                     ServicoDefeito.tipo == tipo).delete()
                for d in lista:
                    self.db.add(ServicoDefeito(id_servico=servico_id, tipo=tipo, defeito=d))

        self.db.commit()
        return self.db.query(ServicoEquipamento).filter(ServicoEquipamento.id_servico == servico_id).first()

    def create_visita(self, chamado_id: int, visita_data: dict) -> Visita:
        servicos_data = visita_data.pop('servicos_realizados', [])

        db_visita = Visita(**visita_data, id_os=chamado_id)
        self.db.add(db_visita)
        self.db.flush()  # Retém na memória pra obter id

        for servico_data in servicos_data:
            self.create_servico_equipamento(db_visita.id_visita, servico_data)

        self.db.commit()
        self.db.refresh(db_visita)
        return db_visita

    def get_visita_by_id(self, visita_id: int) -> Optional[Visita]:
        from sqlalchemy.orm import joinedload
        return self.db.query(Visita).options(
            joinedload(Visita.servicos_realizados)
            .joinedload(ServicoEquipamento.materiais_utilizados)
        ).filter(Visita.id_visita == visita_id).first()

    def get_servicos_by_visita(self, visita_id: int) -> list[ServicoEquipamento]:
        """
        Retorna todos os serviços associados a uma visita.
        Usado pelos endpoints que listam serviços de uma visita.
        """
        return self.db.query(ServicoEquipamento).filter(ServicoEquipamento.id_visita == visita_id).all()

    def create_pausa(self, visita_id: int, pausa_data: dict, por_tecnico_id: Optional[int] = None) -> Pausa:
        visita = self.get_visita_by_id(visita_id)
        if not visita:
            raise HTTPException(status_code=404, detail="Visita não encontrada")

        motivo = pausa_data.get("motivo")
        descricao = pausa_data.get("descricao")

        pausa = Pausa(visita_id=visita_id, motivo=motivo, descricao=descricao, por_tecnico_id=por_tecnico_id,
                      is_ativa=True)
        self.db.add(pausa)
        # Atualiza status do chamado associado para PAUSADO
        self.db.query(OrdemServico).filter(OrdemServico.id_os == visita.id_os).update({"status": StatusChamado.PAUSADO.value})
        self.db.commit()
        self.db.refresh(pausa)
        return pausa

    def get_pausas_by_visita(self, visita_id: int) -> list[Pausa]:
        return self.db.query(Pausa).filter(Pausa.visita_id == visita_id).all()

    def resolve_pausas_for_chamado(self, chamado_id: int) -> int:
        """Marca todas as pausas ativas das visitas pertencentes a um chamado como inativas.
        Retorna o número de registros alterados.
        """
        visitas = self.db.query(Visita).filter(Visita.id_os == chamado_id).all()
        visita_ids = [v.id_visita for v in visitas]
        if not visita_ids:
            return 0
        rows_updated = self.db.query(Pausa).filter(Pausa.visita_id.in_(visita_ids), Pausa.is_ativa == True).update({"is_ativa": False})
        self.db.commit()
        return rows_updated

    def update_visita(self, visita_id: int, update_data: dict) -> Optional[Visita]:
        update_data.pop('servicos_realizados', None)

        # Intercepta arrays de comprovantes
        pedagio_urls = update_data.pop('comprovante_pedagio_urls', None)
        frete_urls = update_data.pop('comprovante_frete_urls', None)

        rows_updated = self.db.query(Visita).filter(Visita.id_visita == visita_id).update(update_data)
        if rows_updated == 0:
            return None

        if pedagio_urls is not None:
            self.db.query(Comprovante).filter(Comprovante.id_visita == visita_id,
                                              Comprovante.tipo == 'pedagio').delete()
            for url in pedagio_urls:
                self.db.add(Comprovante(id_visita=visita_id, tipo='pedagio', url=url))

        if frete_urls is not None:
            self.db.query(Comprovante).filter(Comprovante.id_visita == visita_id, Comprovante.tipo == 'frete').delete()
            for url in frete_urls:
                self.db.add(Comprovante(id_visita=visita_id, tipo='frete', url=url))

        self.db.commit()
        return self.get_visita_by_id(visita_id)

    def update_visita_e_chamado(
            self,
            visita_id: int,
            chamado_id: int,
            visita_in: VisitaUpdate
    ) -> Optional[Visita]:
        """
        Atualiza uma visita e, se necessário, o status do chamado pai, validando as regras de negócio para finalização.
        Tudo em uma única transação.
        """
        try:
            visita_db = self.get_visita_by_id(visita_id)
            if not visita_db or visita_db.id_os != chamado_id:
                return None

            update_data = visita_in.dict(exclude_unset=True)
            if not update_data:
                return visita_db

            for key, value in update_data.items():
                if hasattr(visita_db, key):
                    if key in ('comprovante_pedagio_urls', 'comprovante_frete_urls', 'servicos_realizados'):
                        setattr(visita_db, key, value)
                    else:
                        setattr(visita_db, key, value)
            dados_update_chamado = {}
            if visita_db.servico_finalizado is True:
                if visita_db.km_total > 0:
                    if not visita_db.odometro_inicio_url or not visita_db.odometro_fim_url:
                        raise HTTPException(status_code=400,
                                            detail="Fotos do odômetro (início e fim) são obrigatórias se km_total > 0.")
                if visita_db.valor_pedagio > 0:
                    if not visita_db.comprovante_pedagio_urls:
                        raise HTTPException(status_code=400,
                                            detail="Comprovante(s) de pedágio são obrigatórios se valor_pedagio > 0.")
                if visita_db.valor_frete_devolucao > 0:
                    if not visita_db.comprovante_frete_urls:
                        raise HTTPException(status_code=400,
                                            detail="Comprovante(s) de frete são obrigatórios se valor_frete_devolucao > 0.")

                dados_update_chamado = {"status": StatusChamado.FINALIZADO.value, "data_conclusao": date.today()}

            elif visita_db.servico_finalizado is False:
                pendencia = visita_db.pendencia
                dados_update_chamado = {
                    "status": StatusChamado.PENDENTE.value if pendencia else StatusChamado.EM_ATENDIMENTO.value,
                    "data_conclusao": None
                }

            self.db.add(visita_db)

            if dados_update_chamado:
                self.db.query(OrdemServico).filter(OrdemServico.id_os == chamado_id).update(dados_update_chamado)

            self.db.commit()

        except HTTPException as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            raise e

        self.db.refresh(visita_db)
        return visita_db
