// Ponto de entrada da camada offline-first (SDD 6.12).
export * from "./acoes";
export * from "./cacheOS";
export * from "./sessao";
export * from "./store";
export * from "./tipos";
export { sincronizar, dispararSync, iniciarSincronizacao } from "./sync";
export { atualizarContagens } from "./status";
export {
  listarEventosPendentes,
  listarEventosRejeitados,
} from "./outbox";
