// Dados do cliente da OS (endereco) com copia local. Nao faz parte do contrato de /api/sync,
// entao so ficam disponiveis offline se a OS ja foi aberta uma vez com internet.
import { Cliente, getClientePorId } from "@/api/cliente";
import { gravarMeta, lerMeta } from "./db";

const chave = (id: number) => `cliente_${id}`;

export async function obterClienteComCache(id: number): Promise<Cliente> {
  try {
    const c = await getClientePorId(id);
    await gravarMeta(chave(id), JSON.stringify(c)).catch(() => undefined);
    return c;
  } catch (err) {
    const guardado = await lerMeta(chave(id)).catch(() => null);
    if (guardado) {
      try {
        return JSON.parse(guardado) as Cliente;
      } catch {
        // copia corrompida: propaga o erro original
      }
    }
    throw err;
  }
}
