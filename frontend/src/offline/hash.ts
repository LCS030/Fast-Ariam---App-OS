// Integridade dos arquivos da fila: SHA-256 calculado NO APARELHO, na captura.
//
// O hash e calculado quando o arquivo entra na fila (copiarParaFila / salvarAssinaturaNaFila) e guardado no SQLite
// junto da linha da fila. Ao enviar, o app manda esse hash e o servidor recalcula sobre os bytes que recebeu: se for
// diferente (arquivo corrompido em transito OU alterado enquanto esperava horas na fila), responde 422 HASH_DIVERGENTE.
// Calcular so no momento do envio nao provaria nada sobre o periodo offline.
import { File } from "expo-file-system";
import * as Crypto from "expo-crypto";

function paraHex(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let hex = "";
  for (let i = 0; i < bytes.length; i++) hex += bytes[i].toString(16).padStart(2, "0");
  return hex;
}

/** SHA-256 (64 hex minusculos) do arquivo em `caminho` (URI file://). Lanca erro se nao conseguir ler. */
export async function sha256DoArquivo(caminho: string): Promise<string> {
  const bytes = await new File(caminho).bytes(); // ate 15 MB: cabe na memoria
  const digest = await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, bytes);
  return paraHex(digest);
}
