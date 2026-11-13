"""
Integridade da visita: selo HMAC-SHA256 e verificação (pilar Integridade).

O QUE É: ao finalizar o atendimento, monta-se um JSON canônico com os dados que não podem mudar depois da assinatura
e grava-se `HMAC-SHA256(INTEGRITY_KEY, json)` em `visita.selo_integridade`. Quem altera o banco diretamente (ex.: pelo
painel do Supabase) não consegue recalcular o selo sem a chave; `GET /api/chamados/{id}/verificar-integridade` recalcula
e acusa `adulterado`. Também re-hasheia os arquivos em disco contra os SHA-256 gravados.

COBERTURA (decisão registrada na SDD): o selo é POR VISITA e cobre SOMENTE o que não pode mais mudar depois do fim do
atendimento — horários/km da ida, cliente (nome/CPF/assinatura), equipamentos (ids e série), defeitos, conserto, materiais
e as fotos de serviço (com hash). REGRA DE OURO: nada que o fluxo normal ainda altere até o fim da volta pode entrar no
selo, senão ele acusa "adulterado" numa OS legítima. Por isso ficam FORA: volta, km_total, custo, pedágio, frete,
comprovantes (chegam até o fim da volta), fotos da ida (podem ser reenviadas até a OS finalizar) e o técnico atribuído
(pode ser desativado/desatribuído antes da volta). O que ficou de fora de SELO continua CONFERIDO por hash na verificação
(arquivos) e por `log_acao` (quem finalizou). Correção administrativa pós-finalização (RN-49: fotos e materiais) RESSELA
a visita e audita o selo anterior/novo em `log_acao`. Visitas finalizadas antes desta versão ficam `sem_selo` (não são
seladas retroativamente: selar agora validaria dados que podem já ter sido alterados).

SELO REMOVIDO: o selo também é gravado no `log_acao` (ATENDIMENTO_FINALIZADO / SELO_RESSELADO). Se `selo_integridade` for
anulado no banco mas o log registra que a visita foi selada, a verificação acusa `selo_removido` (adulterado), e não
`sem_selo`. Visita sem selo e sem registro de selo no log é legado (`sem_selo`).

LIMITES: HMAC prova que quem selou tinha a chave (o servidor) — não é assinatura digital de terceiros nem prova autoria
do cliente (a imagem da assinatura NÃO é não repúdio criptográfico). Evidência de adulteração do banco, não de autoria.
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text

from app.core import config
from app.core.crypto import ErroDecifragem, TextoCifrado, decifrar, esta_cifrado
from app.models.comprovante import Comprovante
from app.models.log_acao import LogAcao
from app.models.material import Material
from app.models.servico_defeito import ServicoDefeito
from app.models.servico_equipamento import ServicoEquipamento
from app.models.servico_foto import ServicoFoto
from app.models.visita import Visita
from app.services import auditoria_service as auditoria
from app.services import file_service

logger = logging.getLogger(__name__)

SELO_VERSAO = 1

INTEGRO = "integro"
ADULTERADO = "adulterado"
SEM_SELO = "sem_selo"
NAO_FINALIZADA = "nao_finalizada"


# ---------------------------------------------------------------------------------------------------------------------
# JSON canônico + HMAC
# ---------------------------------------------------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    """Instante em UTC com microssegundos fixos (naive é tratado como UTC, como o resto do sistema)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _dinheiro(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    return str(Decimal(str(valor)).quantize(Decimal("0.01")))


def montar_payload(db, chamado, visita) -> Dict[str, Any]:
    """Dados da visita que o selo protege. Lê do banco/sessão (faz flush antes: a sessão usa autoflush=False)."""
    db.flush()
    servicos: List[Dict[str, Any]] = []
    q = db.query(ServicoEquipamento).filter(ServicoEquipamento.id_visita == visita.id_visita)
    for s in q.order_by(ServicoEquipamento.id_servico).all():
        defeitos = db.query(ServicoDefeito).filter(ServicoDefeito.id_servico == s.id_servico).all()
        fotos = db.query(ServicoFoto).filter(ServicoFoto.id_servico == s.id_servico).all()
        materiais = db.query(Material).filter(Material.id_servico == s.id_servico).all()
        equip = s.equipamento
        servicos.append({
            "id_servico": s.id_servico,
            "id_os_equipamento": s.id_os_equipamento,
            # Só ids e série (travados). O NOME do modelo pode ser renomeado pelo admin e reescreve o histórico exibido.
            "id_equipamento_modelo": getattr(equip, "id_equipamento_modelo", None),
            "numero_serie": getattr(equip, "numero_serie", None) or s.numero_serie_atendido,
            "conserto_salvo_em": _iso(s.conserto_salvo_em),
            "defeito_outros_descricao": s.defeito_outros_descricao,
            "vazamento_ponto_descricao": s.vazamento_ponto_descricao,
            "defeitos": sorted([d.tipo, d.defeito] for d in defeitos),
            "materiais": sorted([m.nome, int(m.quantidade), _dinheiro(m.valor)] for m in materiais),
            "fotos": sorted([f.tipo, f.url, f.sha256] for f in fotos),
        })
    return {
        "versao": SELO_VERSAO,
        "id_os": chamado.id_os,
        "id_visita": visita.id_visita,
        "data_visita": visita.data_visita.isoformat() if visita.data_visita else None,
        "ida_inicio_em": _iso(visita.ida_inicio_em),
        "ida_fim_em": _iso(visita.ida_fim_em),
        "atendimento_inicio_em": _iso(visita.atendimento_inicio_em),
        "atendimento_fim_em": _iso(visita.atendimento_fim_em),
        "km_inicio_ida": visita.km_inicio_ida,
        "km_fim_ida": visita.km_fim_ida,
        "nome_cliente": visita.nome_cliente_assinatura,
        "documento_cliente": visita.documento_cliente,
        "assinatura_url": visita.assinatura_url,
        "assinatura_sha256": visita.assinatura_sha256,
        "servicos": servicos,
    }


def arquivos_da_visita(db, visita) -> List[tuple]:
    """
    (rótulo, url, sha256 esperado) de TODO arquivo da visita, selado ou não: assinatura, fotos de odômetro/deslocamento,
    comprovantes e fotos de serviço. A verificação re-hasheia cada um em disco. Fica separado do selo de propósito: estes
    arquivos podem mudar legitimamente até o fim da volta, mas continuam tendo o hash conferido.
    """
    itens: List[tuple] = [("assinatura", visita.assinatura_url, visita.assinatura_sha256)]
    for campo, sha in (visita.arquivos_sha256 or {}).items():
        itens.append((campo, getattr(visita, campo, None), sha))
    for c in db.query(Comprovante).filter(Comprovante.id_visita == visita.id_visita).all():
        itens.append((f"comprovante_{c.tipo}", c.url, c.sha256))
    for sv in db.query(ServicoEquipamento).filter(ServicoEquipamento.id_visita == visita.id_visita).all():
        for f in db.query(ServicoFoto).filter(ServicoFoto.id_servico == sv.id_servico).all():
            itens.append((f"foto_{f.tipo}_servico_{sv.id_servico}", f.url, f.sha256))
    return itens


def serializar_canonico(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def calcular_selo(payload: Dict[str, Any]) -> str:
    return hmac.new(config.INTEGRITY_KEY, serializar_canonico(payload), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# Selar / resselar
# ---------------------------------------------------------------------------------------------------------------------

def selar_visita(db, chamado, visita) -> str:
    """Grava o selo na visita (sem commit: o chamador confirma junto com a ação). Retorna o selo."""
    selo = calcular_selo(montar_payload(db, chamado, visita))
    visita.selo_integridade = selo
    visita.selo_versao = SELO_VERSAO
    return selo


def resselar_visita(db, chamado, visita, usuario: dict, motivo: str) -> None:
    """
    Correção administrativa pós-finalização (RN-49): recalcula o selo de uma visita JÁ selada e registra o anterior e o
    novo. Visita sem selo (legado) continua sem selo. Sem commit.
    """
    if not visita.selo_integridade:
        return
    anterior = visita.selo_integridade
    novo = selar_visita(db, chamado, visita)
    auditoria.registrar_acao(db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.SELO_RESSELADO,
                             payload={"id_visita": visita.id_visita, "motivo": motivo,
                                      "selo_anterior": anterior, "selo_novo": novo})


# ---------------------------------------------------------------------------------------------------------------------
# Verificação
# ---------------------------------------------------------------------------------------------------------------------

def _conferir_arquivo(motivos: List[str], rotulo: str, url: Optional[str], esperado: Optional[str]) -> None:
    if not url or not esperado:  # sem URL ou sem hash gravado (legado): nada a conferir
        return
    try:
        dados = file_service.ler_arquivo_por_url(url)
    except ErroDecifragem:
        motivos.append(f"arquivo_adulterado:{rotulo}")
        return
    if dados is None:
        motivos.append(f"arquivo_ausente:{rotulo}")
    elif not hmac.compare_digest(file_service.sha256_hex(dados), esperado):
        motivos.append(f"arquivo_divergente:{rotulo}")


def selo_auditado(db, chamado, visita) -> Optional[str]:
    """
    Último selo registrado no `log_acao` para a visita (ATENDIMENTO_FINALIZADO, depois SELO_RESSELADO). É a "segunda
    cópia" do selo: quem anula `visita.selo_integridade` no banco continua exposto por este registro.
    """
    ultimo: Optional[str] = None
    acoes = (auditoria.ATENDIMENTO_FINALIZADO, auditoria.SELO_RESSELADO)
    for reg in (db.query(LogAcao).filter(LogAcao.id_os == chamado.id_os, LogAcao.acao.in_(acoes))
                .order_by(LogAcao.id).all()):
        dados = reg.payload or {}
        if dados.get("id_visita") != visita.id_visita:
            continue
        selo = dados.get("selo") if reg.acao == auditoria.ATENDIMENTO_FINALIZADO else dados.get("selo_novo")
        if selo:
            ultimo = selo
    return ultimo


def verificar_visita(db, chamado, visita) -> Dict[str, Any]:
    if visita.atendimento_fim_em is None:
        return {"id_visita": visita.id_visita, "estado": NAO_FINALIZADA, "motivos": []}
    auditado = selo_auditado(db, chamado, visita)
    if not visita.selo_integridade:
        if auditado:  # foi selada e alguém apagou o selo: isto é adulteração, não legado
            return {"id_visita": visita.id_visita, "estado": ADULTERADO, "motivos": ["selo_removido"]}
        return {"id_visita": visita.id_visita, "estado": SEM_SELO, "motivos": []}
    motivos: List[str] = []
    payload = montar_payload(db, chamado, visita)
    if visita.selo_versao != SELO_VERSAO:
        motivos.append("versao_do_selo_desconhecida")
    elif not hmac.compare_digest(calcular_selo(payload), visita.selo_integridade):
        motivos.append("selo_divergente")
    if auditado and not hmac.compare_digest(auditado, visita.selo_integridade):
        motivos.append("selo_diverge_da_auditoria")
    # Arquivos: recalcula o SHA-256 do que está em disco e compara com o gravado (pega troca de arquivo sem mexer no banco).
    for rotulo, url, esperado in arquivos_da_visita(db, visita):
        _conferir_arquivo(motivos, rotulo, url, esperado)
    return {"id_visita": visita.id_visita, "estado": ADULTERADO if motivos else INTEGRO, "motivos": motivos}


def _campos_cifrados_invalidos(db, id_visita: int) -> List[str]:
    """
    Colunas `TextoCifrado` da visita cujo valor bruto NAO e valido: texto puro (com o modo legado desligado) ou `enc1:` que
    nao autentica (adulterado, de outra coluna ou chave errada). Le o valor BRUTO (SQL), nunca o devolve nem o registra:
    so os nomes das colunas.
    """
    colunas = [c.name for c in Visita.__table__.columns if isinstance(c.type, TextoCifrado)]
    contextos = {c.name: c.type.contexto for c in Visita.__table__.columns if isinstance(c.type, TextoCifrado)}
    linha = db.execute(text(f"SELECT {', '.join(colunas)} FROM visita WHERE id_visita = :i"), {"i": id_visita}).fetchone()
    invalidas: List[str] = []
    for nome, valor in zip(colunas, linha or ()):
        if valor is None:
            continue
        if not esta_cifrado(valor):
            if not config.ENCRYPTION_ALLOW_LEGACY_PLAINTEXT:
                invalidas.append(nome)
            continue
        try:
            decifrar(valor, contextos[nome])
        except (ErroDecifragem, UnicodeDecodeError):
            invalidas.append(nome)
    return invalidas


def _visitas_para_verificar(db, chamado):
    """
    (id_visita, Visita ou None) por visita da OS. Uma visita cujo campo cifrado nao decifra NAO pode ser carregada pelo ORM
    (ErroDecifragem): vem como None e vira `adulterado` com `campo_cifrado_invalido:<coluna>` em vez de derrubar o laudo (500).
    """
    ids = [i for (i,) in db.execute(select(Visita.id_visita).where(Visita.id_os == chamado.id_os)
                                    .order_by(Visita.id_visita)).fetchall()]
    for id_ in ids:
        try:
            yield id_, db.get(Visita, id_)
        except (ErroDecifragem, UnicodeDecodeError):
            yield id_, None


def verificar_chamado(db, chamado) -> Dict[str, Any]:
    visitas = []
    for id_visita, visita in _visitas_para_verificar(db, chamado):
        if visita is not None:
            visitas.append(verificar_visita(db, chamado, visita))
            continue
        campos = _campos_cifrados_invalidos(db, id_visita) or ["desconhecido"]
        logger.error("Visita %s: campo cifrado invalido (%s); verificacao de integridade = adulterado.",
                     id_visita, ", ".join(campos))
        visitas.append({"id_visita": id_visita, "estado": ADULTERADO,
                        "motivos": [f"campo_cifrado_invalido:{c}" for c in campos]})
    estados = {v["estado"] for v in visitas}
    if ADULTERADO in estados:
        geral = ADULTERADO
    elif INTEGRO in estados:
        geral = INTEGRO
    elif SEM_SELO in estados:
        geral = SEM_SELO
    else:
        geral = NAO_FINALIZADA
    return {"id_os": chamado.id_os, "estado": geral, "visitas": visitas}
