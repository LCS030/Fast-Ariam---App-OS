from sqlalchemy import func, select
from sqlalchemy.orm import Session, configure_mappers, joinedload, selectinload
from typing import List, Optional
from datetime import datetime, timezone
from app.models.tecnico import Tecnico
from app.models.cliente import Cliente
from app.models.chamado import OrdemServico
from app.models.visita import Visita
from app.models.servico_equipamento import ServicoEquipamento
from app.models.material import Material
from app.schemas.tecnico import TecnicoUpdate
from app.schemas.cliente import ClienteUpdate
from app.repositories.in_memory_repository import deep_update
from app.models.comprovante import Comprovante
from app.models.servico_defeito import ServicoDefeito
from app.models.servico_foto import ServicoFoto
from app.models.pausa import Pausa
from app.models.equipamento_modelo import EquipamentoModelo
from app.models.os_equipamento import OsEquipamento


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

    # ------------------------------------------------------------------------------------------------------------
    # Controle de transação. As operações de domínio (services) usam commit=False e confirmam UMA vez no fim, para
    # que ações que tocam várias entidades (ex.: cancelar OS + encerrar pausas + log) sejam atômicas.
    # ------------------------------------------------------------------------------------------------------------
    def add(self, obj) -> None:
        self.db.add(obj)

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def _finish(self, commit: bool) -> None:
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    # ------------------------------------------------------------------------------------------------------------
    # Chamados (OS)
    # ------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _chamado_options():
        """Carrega a árvore usada pelas respostas de uma vez (evita N+1 na serialização)."""
        configure_mappers()  # `Visita.pausas` é um backref: só existe depois da configuração dos mappers
        visitas = selectinload(OrdemServico.visitas)
        servicos = visitas.selectinload(Visita.servicos_realizados)
        return (
            visitas.selectinload(Visita.comprovantes),
            visitas.selectinload(Visita.pausas),
            servicos.selectinload(ServicoEquipamento.materiais_utilizados),
            servicos.selectinload(ServicoEquipamento.defeitos),
            servicos.selectinload(ServicoEquipamento.fotos),
            servicos.selectinload(ServicoEquipamento.equipamento).selectinload(OsEquipamento.equipamento_modelo),
            selectinload(OrdemServico.equipamentos).selectinload(OsEquipamento.equipamento_modelo),
            joinedload(OrdemServico.cliente),
        )

    def get_chamado_by_id(self, chamado_id: int) -> Optional[OrdemServico]:
        return (self.db.query(OrdemServico)
                .options(*self._chamado_options())
                .filter(OrdemServico.id_os == chamado_id)
                .first())

    @staticmethod
    def query_chamado_para_update(chamado_id: int):
        """SELECT ... FOR UPDATE da OS (D11): serializa finalização/cancelamento concorrentes (no-op em SQLite)."""
        return (select(OrdemServico).where(OrdemServico.id_os == chamado_id)
                .with_for_update().execution_options(populate_existing=True))

    def lock_chamado(self, chamado_id: int) -> Optional[OrdemServico]:
        """Trava a linha da OS até o fim da transação e devolve o estado ATUAL (relê o que a sessão tinha em cache)."""
        return self.db.execute(self.query_chamado_para_update(chamado_id)).scalar_one_or_none()

    def get_chamados(self, tecnico_id: Optional[int] = None,
                     is_cancelled: Optional[bool] = None) -> List[OrdemServico]:
        """Lista OS filtrando no SQL (não em Python) e com carga antecipada das relações."""
        query = self.db.query(OrdemServico).options(*self._chamado_options())
        if tecnico_id is not None:
            query = query.filter(OrdemServico.id_tecnico_atribuido == tecnico_id)
        if is_cancelled is not None:
            query = query.filter(OrdemServico.is_cancelled == is_cancelled)
        return query.order_by(OrdemServico.id_os).all()

    def create_chamado(self, chamado_data: dict, commit: bool = True) -> OrdemServico:
        db_chamado = OrdemServico(**chamado_data)
        self.db.add(db_chamado)
        self._finish(commit)
        if commit:
            self.db.refresh(db_chamado)
        return db_chamado

    def update_chamado(self, chamado_id: int, update_data: dict, commit: bool = True) -> Optional[OrdemServico]:
        """Atualiza pelo ORM (não por UPDATE em massa): mantém a sessão coerente e aceita enum ou string."""
        db_chamado = self.db.get(OrdemServico, chamado_id)
        if db_chamado is None:
            return None
        for key, value in update_data.items():
            setattr(db_chamado, key, value)
        self._finish(commit)
        return db_chamado

    # ------------------------------------------------------------------------------------------------------------
    # Serviços por equipamento
    # ------------------------------------------------------------------------------------------------------------
    def create_servico_equipamento(self, visita_id: int, servico_data: dict, commit: bool = True) -> ServicoEquipamento:
        servico_data = dict(servico_data)
        materiais_data = servico_data.pop('materiais_utilizados', None) or []

        defeitos_mapping = {
            'principal': servico_data.pop('defeitos_principais', None) or [],
            'refrigeracao': servico_data.pop('sub_defeitos_refrigeracao', None) or [],
            'compressor': servico_data.pop('sub_defeitos_compressor', None) or [],
            'vazamento': servico_data.pop('sub_defeitos_vazamento', None) or [],
            'outros': servico_data.pop('sub_defeitos_outros', None) or [],
            'iluminacao': servico_data.pop('sub_defeitos_iluminacao', None) or [],
            'estrutura': servico_data.pop('sub_defeitos_estrutura', None) or [],
        }
        # Propriedades somente leitura do model: não são colunas.
        servico_data.pop('fotos_defeito', None)
        servico_data.pop('fotos_conserto', None)
        servico_data.pop('id_servico', None)

        servico = ServicoEquipamento(**servico_data, id_visita=visita_id)

        for m in materiais_data:
            servico.materiais_utilizados.append(Material(**dict(m)))

        for tipo, lista in defeitos_mapping.items():
            for d in lista:
                servico.defeitos.append(ServicoDefeito(tipo=tipo, defeito=str(getattr(d, "value", d))))

        self.db.add(servico)
        self._finish(commit)
        if commit:
            self.db.refresh(servico)
        return servico

    def get_servico_by_id(self, servico_id: int) -> Optional[ServicoEquipamento]:
        return self.db.query(ServicoEquipamento).filter(ServicoEquipamento.id_servico == servico_id).first()

    def update_servico_equipamento(self, servico_id: int, update_data: dict, commit: bool = True):
        servico = self.get_servico_by_id(servico_id)
        if servico is None:
            return None
        update_data = dict(update_data)
        materiais_data = update_data.pop('materiais_utilizados', None)
        update_data.pop('fotos_defeito', None)
        update_data.pop('fotos_conserto', None)
        update_data.pop('id_servico', None)

        defeitos_keys = {
            'defeitos_principais': 'principal',
            'sub_defeitos_refrigeracao': 'refrigeracao',
            'sub_defeitos_compressor': 'compressor',
            'sub_defeitos_vazamento': 'vazamento',
            'sub_defeitos_outros': 'outros',
            'sub_defeitos_iluminacao': 'iluminacao',
            'sub_defeitos_estrutura': 'estrutura',
        }
        defeitos_updates = {}
        for key, tipo in defeitos_keys.items():
            if key in update_data:
                defeitos_updates[tipo] = update_data.pop(key) or []

        for key, value in update_data.items():
            if key in ('defeito_outros_descricao', 'vazamento_ponto_descricao'):  # série/nome: legado, nunca editáveis
                setattr(servico, key, value)

        if materiais_data is not None:
            servico.materiais_utilizados.clear()
            for m in materiais_data:
                servico.materiais_utilizados.append(Material(**dict(m)))

        for tipo, lista in defeitos_updates.items():
            for d in [d for d in servico.defeitos if d.tipo == tipo]:
                servico.defeitos.remove(d)
            for d in lista:
                servico.defeitos.append(ServicoDefeito(tipo=tipo, defeito=str(getattr(d, "value", d))))

        self._finish(commit)
        return servico

    def get_servicos_by_visita(self, visita_id: int, atualizar: bool = False) -> List[ServicoEquipamento]:
        """
        Serviços (com materiais, defeitos, fotos e equipamento da OS) de uma visita. `atualizar=True` relê tudo do
        banco, ignorando o que a sessão já tinha em cache (usado nas travas de início/finalização, TR-12/TR-13).
        """
        query = (self.db.query(ServicoEquipamento)
                 .options(selectinload(ServicoEquipamento.materiais_utilizados),
                          selectinload(ServicoEquipamento.defeitos),
                          selectinload(ServicoEquipamento.fotos),
                          selectinload(ServicoEquipamento.equipamento).selectinload(OsEquipamento.equipamento_modelo))
                 .filter(ServicoEquipamento.id_visita == visita_id)
                 .order_by(ServicoEquipamento.id_servico))
        if atualizar:
            query = query.populate_existing()
        return query.all()

    def get_servicos_do_equipamento(self, os_equipamento_id: int) -> List[ServicoEquipamento]:
        """Registros de serviço do equipamento da OS em TODAS as visitas (inclui histórico)."""
        return (self.db.query(ServicoEquipamento)
                .options(selectinload(ServicoEquipamento.materiais_utilizados),
                         selectinload(ServicoEquipamento.defeitos),
                         selectinload(ServicoEquipamento.fotos))
                .filter(ServicoEquipamento.id_os_equipamento == os_equipamento_id)
                .order_by(ServicoEquipamento.id_servico)
                .all())

    def delete_servico(self, servico: ServicoEquipamento, commit: bool = False) -> None:
        self.db.delete(servico)
        self._finish(commit)

    def get_foto_servico(self, foto_id: int) -> Optional[ServicoFoto]:
        return self.db.query(ServicoFoto).filter(ServicoFoto.id_foto == foto_id).first()

    def delete_foto_servico(self, foto: ServicoFoto, commit: bool = False) -> None:
        """Remove só o REGISTRO da foto; o arquivo não é apagado do armazenamento (sem rotina de purga, RNF-02)."""
        self.db.delete(foto)
        self._finish(commit)

    # ------------------------------------------------------------------------------------------------------------
    # Catálogo de modelos e equipamentos da OS (v0.5)
    # ------------------------------------------------------------------------------------------------------------
    def get_modelo_by_id(self, modelo_id: int) -> Optional[EquipamentoModelo]:
        return self.db.get(EquipamentoModelo, modelo_id)

    def get_modelo_por_nome(self, nome: str) -> Optional[EquipamentoModelo]:
        """Busca sem diferenciar maiúsculas (a unicidade do catálogo é case-insensitive)."""
        return (self.db.query(EquipamentoModelo)
                .filter(func.lower(EquipamentoModelo.modelo) == nome.strip().lower()).first())

    def get_modelos(self, is_active: Optional[bool] = None) -> List[EquipamentoModelo]:
        query = self.db.query(EquipamentoModelo)
        if is_active is not None:
            query = query.filter(EquipamentoModelo.is_active == is_active)
        return query.order_by(func.lower(EquipamentoModelo.modelo)).all()

    def create_modelo(self, nome: str, commit: bool = False) -> EquipamentoModelo:
        modelo = EquipamentoModelo(modelo=nome.strip(), is_active=True)
        self.db.add(modelo)
        self._finish(commit)
        return modelo

    def get_os_equipamento(self, os_equipamento_id: int) -> Optional[OsEquipamento]:
        return (self.db.query(OsEquipamento).options(selectinload(OsEquipamento.equipamento_modelo))
                .filter(OsEquipamento.id_os_equipamento == os_equipamento_id).first())

    def get_os_equipamentos(self, chamado_id: int) -> List[OsEquipamento]:
        return (self.db.query(OsEquipamento).options(selectinload(OsEquipamento.equipamento_modelo))
                .filter(OsEquipamento.id_os == chamado_id).order_by(OsEquipamento.id_os_equipamento).all())

    def get_os_equipamento_por_serie(self, chamado_id: int, numero_serie: str) -> Optional[OsEquipamento]:
        """Série já vinculada à OS (sem diferenciar maiúsculas)."""
        return (self.db.query(OsEquipamento)
                .filter(OsEquipamento.id_os == chamado_id,
                        func.upper(OsEquipamento.numero_serie) == numero_serie.strip().upper()).first())

    def add_os_equipamento(self, chamado_id: int, modelo_id: int, numero_serie: str,
                           commit: bool = False) -> OsEquipamento:
        equipamento = OsEquipamento(id_os=chamado_id, id_equipamento_modelo=modelo_id,
                                    numero_serie=numero_serie.strip(), origem="admin")
        self.db.add(equipamento)
        self._finish(commit)
        return equipamento

    def delete_os_equipamento(self, equipamento: OsEquipamento, commit: bool = False) -> None:
        self.db.delete(equipamento)
        self._finish(commit)

    def add_servico_foto(self, servico_id: int, tipo: str, url: str, commit: bool = True,
                         sha256: Optional[str] = None) -> ServicoFoto:
        foto = ServicoFoto(id_servico=servico_id, tipo=tipo, url=url, sha256=sha256)
        self.db.add(foto)
        self._finish(commit)
        if commit:
            self.db.refresh(foto)
        return foto

    # ------------------------------------------------------------------------------------------------------------
    # Visitas
    # ------------------------------------------------------------------------------------------------------------
    def create_visita(self, chamado_id: int, visita_data: dict, commit: bool = True) -> Visita:
        db_visita = Visita(**visita_data, id_os=chamado_id)
        self.db.add(db_visita)
        self._finish(commit)
        if commit:
            self.db.refresh(db_visita)
        return db_visita

    def get_visita_by_id(self, visita_id: int) -> Optional[Visita]:
        configure_mappers()
        return (self.db.query(Visita)
                .options(selectinload(Visita.comprovantes),
                         selectinload(Visita.pausas),
                         selectinload(Visita.servicos_realizados).selectinload(ServicoEquipamento.materiais_utilizados),
                         selectinload(Visita.servicos_realizados).selectinload(ServicoEquipamento.defeitos),
                         selectinload(Visita.servicos_realizados).selectinload(ServicoEquipamento.fotos),
                         selectinload(Visita.servicos_realizados).selectinload(ServicoEquipamento.equipamento)
                         .selectinload(OsEquipamento.equipamento_modelo))
                .filter(Visita.id_visita == visita_id)
                .first())

    def get_visita_aberta(self, chamado_id: int) -> Optional[Visita]:
        """
        Visita executável da OS: a MAIS RECENTE, desde que não finalizada; senão None.
        Visitas anteriores não finalizadas são "abandonadas" (ex.: técnico desativado, RN-08a): ficam só como
        histórico e nunca voltam a ser executáveis. Invariante: no máximo uma visita aberta executável por OS.
        """
        ultima = self.get_ultima_visita(chamado_id)
        return ultima if ultima is not None and not ultima.servico_finalizado else None

    def get_ultima_visita(self, chamado_id: int) -> Optional[Visita]:
        return (self.db.query(Visita).filter(Visita.id_os == chamado_id)
                .order_by(Visita.id_visita.desc()).first())

    def update_visita(self, visita_id: int, update_data: dict, commit: bool = True) -> Optional[Visita]:
        """Atualiza colunas da visita pelo ORM. Chaves que não são colunas (listas derivadas etc.) são ignoradas."""
        visita = self.db.get(Visita, visita_id)
        if visita is None:
            return None
        colunas = {c.key for c in Visita.__table__.columns}
        for key, value in update_data.items():
            if key in colunas and key != 'id_visita':
                setattr(visita, key, value)
        self._finish(commit)
        return self.get_visita_by_id(visita_id)

    def set_arquivo_visita(self, visita_id: int, campo: str, url: str, sha256: Optional[str],
                           commit: bool = True) -> Optional[Visita]:
        """Grava a URL de uma foto de odometro/deslocamento na visita e o SHA-256 do arquivo em `arquivos_sha256`."""
        visita = self.db.get(Visita, visita_id)
        if visita is None:
            return None
        setattr(visita, campo, url)
        hashes = dict(visita.arquivos_sha256 or {})  # novo dict: o ORM só detecta a mudança de JSON por atribuição
        if sha256:
            hashes[campo] = sha256
        else:
            hashes.pop(campo, None)
        visita.arquivos_sha256 = hashes
        self._finish(commit)
        return visita

    def add_comprovante(self, visita_id: int, tipo: str, url: str, commit: bool = True,
                        sha256: Optional[str] = None) -> Comprovante:
        """Registra um comprovante ('pedagio' ou 'frete') na tabela `comprovante` (SDD 4.6)."""
        comprovante = Comprovante(id_visita=visita_id, tipo=tipo, url=url, sha256=sha256)
        self.db.add(comprovante)
        self._finish(commit)
        return comprovante

    # ------------------------------------------------------------------------------------------------------------
    # Pausas
    # ------------------------------------------------------------------------------------------------------------
    def create_pausa(self, visita_id: int, pausa_data: dict, por_usuario_id: Optional[int] = None,
                     por_papel: Optional[str] = None, commit: bool = True) -> Pausa:
        """Cria a pausa. A mudança de status da OS é decidida pelo service (validador de transições)."""
        pausa = Pausa(visita_id=visita_id, motivo=pausa_data.get("motivo"), descricao=pausa_data.get("descricao"),
                      por_usuario_id=por_usuario_id, por_papel=por_papel, is_ativa=True)
        if pausa_data.get("criado_em") is not None:
            pausa.criado_em = pausa_data["criado_em"]
        self.db.add(pausa)
        self._finish(commit)
        if commit:
            self.db.refresh(pausa)
        return pausa

    def get_pausas_by_visita(self, visita_id: int) -> List[Pausa]:
        return self.db.query(Pausa).filter(Pausa.visita_id == visita_id).order_by(Pausa.id_pausa).all()

    def resolve_pausas_for_chamado(self, chamado_id: int, quando: Optional[datetime] = None,
                                   commit: bool = False) -> int:
        """Encerra (is_ativa=false, encerrada_em) todas as pausas ativas das visitas da OS. Retorna quantas."""
        quando = quando or datetime.now(timezone.utc)
        pausas = (self.db.query(Pausa)
                  .join(Visita, Visita.id_visita == Pausa.visita_id)
                  .filter(Visita.id_os == chamado_id, Pausa.is_ativa.is_(True))
                  .all())
        for pausa in pausas:
            pausa.is_ativa = False
            pausa.encerrada_em = quando
        self._finish(commit)
        return len(pausas)
