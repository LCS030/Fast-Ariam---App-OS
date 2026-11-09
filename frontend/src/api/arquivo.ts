// Montagem de arquivos de imagem para multipart/form-data.
import { sha256DoArquivo } from "@/offline/hash";

export interface ArquivoImagem {
  uri: string;
  mime: "image/jpeg" | "image/png";
}

// Timeout maior que o padrao: uploads de ate 15 MB em rede movel.
export const UPLOAD_TIMEOUT_MS = 120000;

export function anexarImagem(
  form: FormData,
  campo: string,
  arquivo: ArquivoImagem,
  prefixo: string
): void {
  const ext = arquivo.mime === "image/png" ? "png" : "jpg";
  form.append(campo, {
    uri: arquivo.uri,
    type: arquivo.mime,
    name: `${prefixo}_${Date.now()}.${ext}`,
  } as unknown as Blob);
}

/**
 * Como `anexarImagem`, mas calcula o SHA-256 do arquivo e o envia no campo `sha256`. O servidor recalcula e responde
 * 422 HASH_DIVERGENTE se for diferente; com SHA256_ORIGEM_OBRIGATORIO=true, sem este campo o upload e recusado
 * (422 HASH_AUSENTE). Use SEMPRE esta funcao nos envios diretos (a fila offline ja grava o hash na captura).
 */
export async function anexarImagemComHash(
  form: FormData,
  campo: string,
  arquivo: ArquivoImagem,
  prefixo: string
): Promise<void> {
  form.append("sha256", await sha256DoArquivo(arquivo.uri));
  anexarImagem(form, campo, arquivo, prefixo);
}
