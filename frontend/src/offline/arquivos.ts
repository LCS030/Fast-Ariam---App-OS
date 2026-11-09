// Armazenamento PRIVADO dos arquivos da fila (fotos, comprovantes, assinatura).
// documentDirectory fica no sandbox do app (nao e galeria nem armazenamento compartilhado) e
// sobrevive ao fechamento do app; o cache da camera nao serve porque o Android pode limpa-lo.
import * as FileSystem from "expo-file-system/legacy";
import type { ArquivoImagem } from "@/api/arquivo";
import { ErroOffline } from "./tipos";

function dirFila(): string {
  const base = FileSystem.documentDirectory;
  if (!base) throw new ErroOffline("SEM_ARMAZENAMENTO", "Armazenamento do aparelho indisponível.");
  return `${base}outbox/`;
}

async function garantirDir(): Promise<string> {
  const dir = dirFila();
  const info = await FileSystem.getInfoAsync(dir);
  if (!info.exists) await FileSystem.makeDirectoryAsync(dir, { intermediates: true });
  return dir;
}

const extensao = (mime: "image/jpeg" | "image/png") => (mime === "image/png" ? "png" : "jpg");

/** Copia a imagem capturada (cache da camera) para o armazenamento privado da fila. */
export async function copiarParaFila(arquivo: ArquivoImagem, clientFileId: string): Promise<string> {
  const dir = await garantirDir();
  const destino = `${dir}${clientFileId}.${extensao(arquivo.mime)}`;
  await FileSystem.copyAsync({ from: arquivo.uri, to: destino });
  const info = await FileSystem.getInfoAsync(destino);
  if (!info.exists) {
    throw new ErroOffline("COPIA_FALHOU", "Não foi possível salvar a foto no aparelho. Tire a foto novamente.");
  }
  return destino;
}

/** Grava a assinatura (data URI PNG vinda do canvas) como arquivo PNG na fila. */
export async function salvarAssinaturaNaFila(
  assinaturaBase64: string,
  clientFileId: string
): Promise<string> {
  const dir = await garantirDir();
  const puro = assinaturaBase64.replace(/^data:image\/\w+;base64,/, "");
  const destino = `${dir}${clientFileId}.png`;
  await FileSystem.writeAsStringAsync(destino, puro, { encoding: FileSystem.EncodingType.Base64 });
  const info = await FileSystem.getInfoAsync(destino);
  if (!info.exists) {
    throw new ErroOffline("COPIA_FALHOU", "Não foi possível salvar a assinatura no aparelho.");
  }
  return destino;
}

export async function arquivoExiste(caminho: string): Promise<boolean> {
  try {
    return (await FileSystem.getInfoAsync(caminho)).exists;
  } catch {
    return false;
  }
}

/** Libera o espaco de um arquivo JA confirmado pelo servidor (nunca chamar antes da confirmacao). */
export async function removerArquivoLocal(caminho: string): Promise<void> {
  try {
    await FileSystem.deleteAsync(caminho, { idempotent: true });
  } catch {
    // melhor esforco: sobrar um arquivo e inofensivo, perder um pendente nao
  }
}
