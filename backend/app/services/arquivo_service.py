"""Autorização de arquivos por OS: um arquivo só pode ser lido pela rota da OS à qual realmente pertence (anti-IDOR)."""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.comprovante import Comprovante
from app.models.servico_equipamento import ServicoEquipamento
from app.models.servico_foto import ServicoFoto
from app.models.visita import Visita

# Colunas da visita que guardam a referência de uma foto de odômetro/deslocamento. A assinatura NÃO entra aqui: ela tem
# rota própria (`.../assinatura`) e nunca é entregue por `arquivos/conteudo`.
CAMPOS_FOTO_DA_VISITA = ("odometro_inicio_url", "odometro_fim_url", "foto_inicio_ida_url", "foto_fim_ida_url",
                         "foto_inicio_volta_url", "foto_fim_volta_url")


def foto_pertence_a_os(db: Session, id_os: int, url: str) -> bool:
    """True se `url` é foto de serviço, comprovante ou foto de odômetro/deslocamento de alguma visita DESTA OS."""
    if db.query(Visita.id_visita).filter(
            Visita.id_os == id_os, or_(*[getattr(Visita, c) == url for c in CAMPOS_FOTO_DA_VISITA])).first():
        return True
    if (db.query(Comprovante.id_comprovante).join(Visita, Visita.id_visita == Comprovante.id_visita)
            .filter(Visita.id_os == id_os, Comprovante.url == url).first()):
        return True
    return bool(
        db.query(ServicoFoto.id_foto)
        .join(ServicoEquipamento, ServicoEquipamento.id_servico == ServicoFoto.id_servico)
        .join(Visita, Visita.id_visita == ServicoEquipamento.id_visita)
        .filter(Visita.id_os == id_os, ServicoFoto.url == url).first())
