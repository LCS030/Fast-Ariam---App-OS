import type { ConfigContext, ExpoConfig } from "expo/config";

/**
 * Configuracao dinamica do app (estende o app.json).
 *
 * Confidencialidade em transito: o Android so permite HTTP puro se `usesCleartextTraffic` estiver ligado. POR PADRAO
 * ele fica DESLIGADO (todo trafego exige HTTPS, mesmo que alguem aponte a API para http://). So para desenvolvimento
 * local contra http://10.0.2.2:8000 ligue-o de forma explicita ao gerar o app nativo:
 *
 *   ALLOW_CLEARTEXT=true npx expo prebuild --clean     (PowerShell: $env:ALLOW_CLEARTEXT="true"; npx expo prebuild --clean)
 *
 * Nunca ligue ALLOW_CLEARTEXT em build de producao. (No Expo Go o plugin nao tem efeito.)
 */
const PERMITIR_HTTP_PURO = process.env.ALLOW_CLEARTEXT === "true";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...(config as ExpoConfig),
  plugins: [
    ...(config.plugins ?? []),
    ["expo-build-properties", { android: { usesCleartextTraffic: PERMITIR_HTTP_PURO } }],
  ],
});
