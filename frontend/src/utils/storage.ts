// Armazenamento do token de sessão (SEG-13).
// O JWT fica no armazenamento seguro do Android (Keystore, via expo-secure-store),
// nunca em AsyncStorage (texto puro).
import * as SecureStore from "expo-secure-store";
import AsyncStorage from "@react-native-async-storage/async-storage";

const TOKEN_KEY = "fast_ariam_token";
const LEGACY_TOKEN_KEY = "token"; // chave usada antes da migração para SecureStore

/** Remove o token antigo gravado em AsyncStorage (texto puro), se existir. */
async function limparTokenLegado(): Promise<void> {
  try {
    await AsyncStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    // melhor esforço: a limpeza do legado não pode impedir o login
  }
}

export async function setToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
  await limparTokenLegado();
}

export async function getToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Apaga somente o token. Dados pendentes de envio (fila offline, fotos, assinatura)
 * NUNCA devem ser removidos aqui (RN-39): ao perder a sessão o técnico só precisa
 * autenticar de novo.
 */
export async function removeToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  } catch {
    // sem token armazenado ou keystore indisponível: nada a remover
  }
  await limparTokenLegado();
}
