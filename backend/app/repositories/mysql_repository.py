from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date
from app.models.tecnico import Tecnico
from app.models.cliente import Cliente
from app.models.chamado import OrdemServico
from app.models.visita import Visita
from app.models.servico_equipamento import ServicoEquipamento
from app.models.material import Material
from app.schemas.tecnico import TecnicoCreate, TecnicoUpdate
from app.schemas.cliente import ClienteCreate, ClienteUpdate
from app.schemas.chamado import ChamadoCreate, ChamadoUpdate
from app.schemas.visita import VisitaCreate, VisitaUpdate
from app.repositories.in_memory_repository import deep_update


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

        db_tecnico_dict = {}
        for c in db_tecnico.__table__.columns:
            db_tecnico_dict[c.name] = getattr(db_tecnico, c.name)
        merged_data = deep_update(db_tecnico_dict, update_data)

        for key, value in merged_data.items():
            if hasattr(db_tecnico, key):
                setattr(db_tecnico, key, value)
        self.db.add(db_tecnico)
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
        from sqlalchemy.orm import selectinload

        return (
            self.db.query(OrdemServico)
            .options(
                selectinload(OrdemServico.visitas)
                    .selectinload(Visita.servicos_realizados)
                    .selectinload(ServicoEquipamento.materiais_utilizados),
                selectinload(OrdemServico.cliente),
                selectinload(OrdemServico.tecnico)
            )
            .filter(OrdemServico.id_os == chamado_id)
            .first()
    )

    def get_chamados(self) -> list[OrdemServico]:
        from sqlalchemy.orm import selectinload

        return (
            self.db.query(OrdemServico)
            .options(
                selectinload(OrdemServico.visitas)
                    .selectinload(Visita.servicos_realizados)
                    .selectinload(ServicoEquipamento.materiais_utilizados),
                selectinload(OrdemServico.cliente),
                selectinload(OrdemServico.tecnico)
            )
            
        .filter(OrdemServico.is_completed == False)
        .all()
    )

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

    def create_visita(self, chamado_id: int, visita_data: dict) -> Visita:
        servicos_data = visita_data.pop('servicos_realizados', [])

        db_visita = Visita(**visita_data, id_os=chamado_id)

        for servico_data in servicos_data:
            materiais_data = servico_data.pop('materiais_utilizados', [])
            db_servico = ServicoEquipamento(**servico_data)

            for material_data in materiais_data:
                db_servico.materiais_utilizados.append(Material(**material_data))

            db_visita.servicos_realizados.append(db_servico)

        self.db.add(db_visita)
        self.db.commit()
        self.db.refresh(db_visita)
        return db_visita

    def get_visita_by_id(self, visita_id: int) -> Optional[Visita]:
        from sqlalchemy.orm import joinedload
        return self.db.query(Visita).options(
            joinedload(Visita.servicos_realizados)
            .joinedload(ServicoEquipamento.materiais_utilizados)
        ).filter(Visita.id_visita == visita_id).first()

    def update_visita(self, visita_id: int, update_data: dict) -> Optional[Visita]:

        update_data.pop('servicos_realizados', None)

        rows_updated = self.db.query(Visita).filter(Visita.id_visita == visita_id).update(update_data)
        if rows_updated == 0:
            return None
        self.db.commit()
        return self.get_visita_by_id(visita_id)
    
    def get_chamados_tecnico(self, tecnico_id: int):
        return (
            self.db.query(OrdemServico)
            .filter(
                OrdemServico.id_tecnico_atribuido == tecnico_id,
                OrdemServico.is_cancelled == False,
                OrdemServico.is_completed == False 
            )
            .all()
    )

    def create_servico_equipamento(self, visita_id: int, servico_data: dict) -> ServicoEquipamento:
        """Cria 1 registro de serviço vinculado à visita."""
        servico = ServicoEquipamento(**servico_data, id_visita=visita_id)
        self.db.add(servico)
        self.db.commit()
        self.db.refresh(servico)
        return servico

    def get_servicos_by_visita(self, visita_id: int) -> List[ServicoEquipamento]:
        """Lista os serviços da visita."""
        return (
            self.db.query(ServicoEquipamento)
            .filter(ServicoEquipamento.id_visita == visita_id)
            .all()
        )

    def update_servico_equipamento(self, servico_id: int, update_data: dict) -> Optional[ServicoEquipamento]:
        """Atualiza qualquer campo do serviço."""
        rows = (
            self.db.query(ServicoEquipamento)
            .filter(ServicoEquipamento.id_servico == servico_id)
            .update(update_data)
        )
        if rows == 0:
            return None
        self.db.commit()
        return (
            self.db.query(ServicoEquipamento)
            .filter(ServicoEquipamento.id_servico == servico_id)
            .first()
        )