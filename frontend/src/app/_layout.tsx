import React, { useEffect } from "react";
import { Alert } from "react-native";
import { Stack, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { onSessionExpired } from "@/utils/session";
import { atualizarContagens, iniciarSincronizacao } from "@/offline";
import { getDb } from "@/offline/db";

export default function RootLayout() {
  const router = useRouter();

  // Offline-first: abre o banco local, calcula as contagens da fila e liga a sincronizacao
  // (ao abrir o app, ao voltar a conexao, ao voltar ao primeiro plano e a cada intervalo).
  useEffect(() => {
    let parar: (() => void) | undefined;
    let ativo = true;
    getDb()
      .then(() => atualizarContagens())
      .then(() => {
        if (ativo) parar = iniciarSincronizacao();
      })
      .catch(() => {
        // banco indisponivel: as telas mostram o erro ao tentar ler/gravar
      });
    return () => {
      ativo = false;
      parar?.();
    };
  }, []);

  // RN-39: 401 em chamada interativa -> a sessao foi marcada como rejeitada (api.ts) e o tecnico
  // vai ao login. A fila de envio e o cache de OS NAO sao apagados.
  useEffect(() => {
    return onSessionExpired(() => {
      Alert.alert(
        "Sessão expirada",
        "Faça login novamente (com internet). As ações salvas neste aparelho continuam guardadas e serão enviadas depois do login."
      );
      router.replace("/login/indexLogin");
    });
  }, [router]);

  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false }} />
    </>
  );
}
