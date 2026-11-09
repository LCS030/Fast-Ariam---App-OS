import React, { useEffect, useState } from "react";
import { View, ActivityIndicator } from "react-native";
import { Redirect } from "expo-router";
import { avaliarSessao } from "@/offline/sessao";

/**
 * Rota inicial (RN-39). Com sessao valida (ate 24 h desde o ultimo login online) vai para a Home,
 * mesmo sem internet; com JWT expirado tambem entra (modo offline) e a fila espera o novo login.
 * Sem sessao, ou depois de 24 h, vai ao login (que explica o motivo). Nada da fila e apagado.
 */
export default function Index() {
  const [destino, setDestino] = useState<"home" | "login" | null>(null);

  useEffect(() => {
    avaliarSessao()
      .then((a) =>
        setDestino(a.situacao === "ok" || a.situacao === "jwt_expirado" ? "home" : "login")
      )
      .catch(() => setDestino("login"));
  }, []);

  if (!destino) {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return <Redirect href={destino === "home" ? "/Home/indexHome" : "/login/indexLogin"} />;
}
