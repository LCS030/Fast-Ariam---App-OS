"""
Teste REAL do Supabase Storage (privado). Rode UMA vez depois de colocar SUPABASE_URL e SUPABASE_SERVICE_KEY no .env:

    python scripts/testar_storage.py

Faz, no bucket configurado (STORAGE_BUCKET), com um objeto temporario `uploads/_teste_<uuid>.png`:
  1. upload;  2. download autenticado e comparacao byte a byte;  3. nao sobrescreve (segundo upload do mesmo nome falha);
  4. o link PUBLICO do objeto NAO funciona (bucket privado);  5. leitura SEM credencial NAO funciona;
  6. remocao;  7. objeto removido nao e mais encontrado.
Cada item aparece como OK/FALHA. Sai com codigo 1 se algo falhar. Remove o objeto de teste ao final, mesmo se falhar.
Nao imprime a chave de servico.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core import config  # noqa: E402
from app.services.storage_service import SupabaseStorage  # noqa: E402

# PNG 1x1 valido
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")


def main() -> int:
    if config.STORAGE_BACKEND != "supabase":
        print("Defina SUPABASE_URL e SUPABASE_SERVICE_KEY no backend/.env antes de rodar este teste.")
        return 2
    s = SupabaseStorage(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.STORAGE_BUCKET)
    nome = f"_teste_{uuid.uuid4().hex}.png"
    base = f"{config.SUPABASE_URL}/storage/v1/object"
    resultados = []

    def passo(desc: str, ok: bool, extra: str = "") -> None:
        resultados.append(ok)
        print(f"  [{'OK' if ok else 'FALHA'}] {desc}" + (f"  ({extra})" if extra and not ok else ""))

    print(f"Bucket: {config.STORAGE_BUCKET} em {config.SUPABASE_URL}")
    try:
        try:
            s.put("uploads", nome, PNG, "image/png")
            passo("upload", True)
        except Exception as exc:
            passo("upload", False, repr(exc)[:200])
            return 1
        passo("download autenticado devolve os mesmos bytes", s.get("uploads", nome) == PNG)
        try:
            s.put("uploads", nome, b"outro conteudo", "image/png")
            passo("segundo upload do mesmo nome e RECUSADO (sem sobrescrita)", False, "foi aceito")
        except Exception:
            passo("segundo upload do mesmo nome e RECUSADO (sem sobrescrita)", s.get("uploads", nome) == PNG)
        publico = httpx.get(f"{base}/public/{config.STORAGE_BUCKET}/uploads/{nome}", timeout=30)
        passo("link PUBLICO nao entrega o arquivo (bucket privado)", publico.status_code != 200, f"HTTP {publico.status_code}")
        anonimo = httpx.get(f"{base}/authenticated/{config.STORAGE_BUCKET}/uploads/{nome}", timeout=30)
        passo("leitura SEM credencial e negada", anonimo.status_code != 200, f"HTTP {anonimo.status_code}")
    finally:
        try:
            s.delete("uploads", nome)
        except Exception as exc:
            print(f"  AVISO: nao consegui remover o objeto de teste uploads/{nome}: {exc!r}")
    passo("objeto removido nao e mais encontrado", s.get("uploads", nome) is None)
    print("TUDO OK" if all(resultados) else "HA FALHAS")
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
