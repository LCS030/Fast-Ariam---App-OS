"""
Configuração central do backend (SDD seção 2 e 6.11).

Tudo que varia por ambiente vem de variáveis de ambiente / .env. Nenhum segredo é hardcoded.
"""
import base64
import binascii
import logging
import os
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

# --- Ambiente ---------------------------------------------------------------------------------------------------------
# ENV: "development" (padrão), "test" ou "production". Usado como guarda por scripts destrutivos e por CORS.
ENV = os.getenv("ENV", "development").strip().lower()
IS_PRODUCTION = ENV in ("production", "prod")

# --- JWT (SDD 6.2 / SEG-07) -------------------------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

if not SECRET_KEY:
    raise ValueError("SECRET_KEY não definida no .env. Crie um arquivo .env e crie uma SECRET_KEY.")

# Segurança A2: HS256 com chave curta é quebrável por força bruta. Produção exige >= 32 caracteres; em dev apenas avisa.
SECRET_KEY_MIN_LENGTH = 32
if len(SECRET_KEY) < SECRET_KEY_MIN_LENGTH:
    if IS_PRODUCTION:
        raise ValueError(f"SECRET_KEY deve ter pelo menos {SECRET_KEY_MIN_LENGTH} caracteres quando ENV=production.")
    logging.getLogger(__name__).warning(
        "SECRET_KEY tem menos de %d caracteres; use uma chave longa e aleatória (obrigatório em produção).",
        SECRET_KEY_MIN_LENGTH)

# O algoritmo nunca pode vir "livre": somente HMAC simétrico (a SDD v0.3 documenta HS256). Impede "none" por configuração.
if ALGORITHM not in ("HS256", "HS384", "HS512"):
    raise ValueError("ALGORITHM inválido. Use HS256 (padrão), HS384 ou HS512.")


# --- Chaves de cifragem e integridade (Confidencialidade / Integridade) -----------------------------------------------
# Três chaves DISTINTAS, de 32 bytes em base64, uma por finalidade (nunca reutilizar entre si nem com a SECRET_KEY):
#   DATA_ENCRYPTION_KEY -> AES-256-GCM dos campos sensíveis (CPF, dados bancários...) e da assinatura em disco;
#   INDEX_KEY           -> HMAC do índice cego (busca/unicidade de CNPJ sem guardar o valor em claro);
#   INTEGRITY_KEY       -> HMAC-SHA256 do selo de integridade da visita.
# São obrigatórias em TODOS os ambientes: a API não sobe sem elas.
def _chave_32_bytes(nome: str) -> bytes:
    bruto = (os.getenv(nome) or "").strip().strip('"').strip("'")
    if not bruto:
        raise ValueError(f"{nome} não definida no .env. Gere com: "
                         'python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"')
    try:
        chave = base64.b64decode(bruto, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{nome} inválida: deve estar codificada em base64.")
    if len(chave) != 32:
        raise ValueError(f"{nome} inválida: deve ter exatamente 32 bytes (AES-256 / HMAC-SHA256); veio com {len(chave)}.")
    return chave


DATA_ENCRYPTION_KEY: bytes = _chave_32_bytes("DATA_ENCRYPTION_KEY")
INDEX_KEY: bytes = _chave_32_bytes("INDEX_KEY")
INTEGRITY_KEY: bytes = _chave_32_bytes("INTEGRITY_KEY")

if len({DATA_ENCRYPTION_KEY, INDEX_KEY, INTEGRITY_KEY, SECRET_KEY.encode("utf-8")}) < 4:
    raise ValueError("DATA_ENCRYPTION_KEY, INDEX_KEY, INTEGRITY_KEY e SECRET_KEY devem ser todas diferentes entre si.")


def _interpretar_flag(bruto: Optional[str], padrao: bool) -> bool:
    if bruto is None or not bruto.strip():
        return padrao
    return bruto.strip().lower() in ("1", "true", "yes", "sim", "on")


def _flag(nome: str, padrao: bool) -> bool:
    return _interpretar_flag(os.getenv(nome), padrao)


def legacy_plaintext_enabled(raw: Optional[str], production: bool) -> bool:
    """Modo de transição da cifragem. Padrão False; ligado com ENV=production é recusado (a aplicação não inicia)."""
    ligado = _interpretar_flag(raw, False)
    if ligado and production:
        raise ValueError("ENCRYPTION_ALLOW_LEGACY_PLAINTEXT não pode ser true com ENV=production: migre os dados com "
                         "scripts/cifrar_dados_existentes.py e desligue.")
    return ligado


# Modo de TRANSIÇÃO da cifragem. Padrão FALSE (seguro): um valor sem o prefixo "enc1:" numa coluna cifrada é tratado como
# adulteração (erro), não como dado legado — senão quem grava um CPF em claro direto no banco seria aceito sem alarme.
# Só ligue (true) temporariamente, em dev/teste, enquanto houver linhas antigas em texto puro a migrar com
# scripts/cifrar_dados_existentes.py. Em ENV=production ligar é RECUSADO (a aplicação não inicia).
ENCRYPTION_ALLOW_LEGACY_PLAINTEXT: bool = legacy_plaintext_enabled(os.getenv("ENCRYPTION_ALLOW_LEGACY_PLAINTEXT"), IS_PRODUCTION)

# O servidor SEMPRE calcula e grava o SHA-256 de cada arquivo recebido. Esta chave só decide se o hash calculado NO
# APARELHO (campo `sha256`) é obrigatório. Padrão true (app ainda não distribuído); use false só se houver app antigo em uso.
SHA256_ORIGEM_OBRIGATORIO: bool = _flag("SHA256_ORIGEM_OBRIGATORIO", True)


# --- Armazenamento de arquivos (Supabase Storage privado, SEG-09 / PR-03) ---------------------------------------------
# Com SUPABASE_URL + SUPABASE_SERVICE_KEY o backend grava/lê fotos, comprovantes e assinaturas (.enc) no bucket PRIVADO
# STORAGE_BUCKET; sem eles usa o disco local (somente dev/teste). A chave de serviço ignora o RLS: fica SÓ no backend,
# nunca no painel, no app, em log ou no Git. Em ENV=production o Supabase é obrigatório (disco local é efêmero).
SUPABASE_URL: Optional[str] = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/") or None
SUPABASE_SERVICE_KEY: Optional[str] = (os.getenv("SUPABASE_SERVICE_KEY") or "").strip().strip('"').strip("'") or None
STORAGE_BUCKET: str = (os.getenv("STORAGE_BUCKET") or "fast-ariam-privado").strip()


def resolver_storage_backend(url: Optional[str], chave: Optional[str], production: bool) -> str:
    """'supabase' quando URL e chave existem; 'local' quando nenhuma existe (recusado em produção); erro se só uma."""
    if bool(url) != bool(chave):
        raise ValueError("SUPABASE_URL e SUPABASE_SERVICE_KEY devem ser definidas JUNTAS (ou nenhuma, para disco local).")
    if url:
        if not url.lower().startswith("https://"):
            raise ValueError("SUPABASE_URL deve usar https://.")
        return "supabase"
    if production:
        raise ValueError("Em ENV=production os arquivos devem ir para o Supabase Storage: defina SUPABASE_URL e "
                         "SUPABASE_SERVICE_KEY (o disco local do servidor é efêmero e não é privado).")
    return "local"


STORAGE_BACKEND: str = resolver_storage_backend(SUPABASE_URL, SUPABASE_SERVICE_KEY, IS_PRODUCTION)


# --- CORS (SEG-03 / PR-18) --------------------------------------------------------------------------------------------
# Origens usadas apenas em desenvolvimento quando CORS_ORIGINS não é informada (painel Vite e CRA/Next local).
DEFAULT_DEV_CORS_ORIGINS: List[str] = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def parse_cors_origins(raw: Optional[str], production: bool = False) -> List[str]:
    """
    Converte CORS_ORIGINS (lista separada por vírgula) em lista de origens.

    - Sem valor: usa os padrões de desenvolvimento; em produção a variável é obrigatória.
    - "*" é recusado: o middleware usa allow_credentials=True e navegadores rejeitam "*" com credenciais.
    """
    origins = [o.strip().rstrip("/") for o in (raw or "").split(",") if o.strip()]
    if not origins:
        if production:
            raise ValueError("CORS_ORIGINS é obrigatória quando ENV=production (lista separada por vírgula).")
        return list(DEFAULT_DEV_CORS_ORIGINS)
    if "*" in origins:
        raise ValueError("CORS_ORIGINS não pode conter '*' (a API usa allow_credentials=True). Liste as origens.")
    return origins


CORS_ORIGINS: List[str] = parse_cors_origins(os.getenv("CORS_ORIGINS"), production=IS_PRODUCTION)


# --- Criação automática de tabelas (PR-19) ----------------------------------------------------------------------------
def auto_create_tables_enabled(raw: Optional[str], production: bool) -> bool:
    """
    AUTO_CREATE_TABLES=true liga Base.metadata.create_all no startup. Só para dev/test: o schema de produção
    evolui por migração versionada (DBA), nunca por create_all. Em produção a variável é recusada.
    """
    ligado = (raw or "").strip().lower() in ("1", "true", "yes", "sim", "on")
    if ligado and production:
        raise ValueError("AUTO_CREATE_TABLES não pode ser habilitada com ENV=production. Use migrações.")
    return ligado


AUTO_CREATE_TABLES: bool = auto_create_tables_enabled(os.getenv("AUTO_CREATE_TABLES"), IS_PRODUCTION)


# --- Valores globais de referência de custo (SDD 6.11 / PR-22 / PR-33 / RN-32) -----------------------------------------
# Valores GLOBAIS do sistema: não são por técnico e o técnico não os altera. Não existe endpoint de configuração por
# técnico. Ajudantes estão fora do escopo v0.3 (chaves de ajudante removidas). O snapshot em custo_os é do Backend A.
# Pendência: a tabela configuracao_custo (DBA) deve passar a ser a fonte; estes valores são o fallback atual.
VALORES_ASSISTENCIA = {
    "PRIMEIRA_HORA_TECNICO": 87.01,
    "HORA_TECNICO": 62.15,
    "TEMPO_DESLOCAMENTO_TECNICO": 24.86,
    "QUILOMETRAGEM": 1.15,
}
