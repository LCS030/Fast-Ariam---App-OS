// Montagem de arquivos de imagem para multipart/form-data.

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
