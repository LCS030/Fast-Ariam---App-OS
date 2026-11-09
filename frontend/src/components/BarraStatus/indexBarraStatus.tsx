import React from "react";
import { Text, TouchableOpacity, View, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { colors } from "@/styles/Colors";
import { irParaPendencias } from "@/utils/nav";
import { useStatusOffline } from "@/offline/store";

/**
 * Indicador global (RF-21): conexao, envio em andamento, acoes pendentes/rejeitadas e problemas
 * de sessao. Fica logo abaixo do cabecalho em todas as telas; tocar abre a tela de pendencias.
 */
export function BarraStatus() {
  const router = useRouter();
  const s = useStatusOffline();

  if (s.situacaoSessao === "sem_sessao") return null; // login: nada a mostrar

  const partes: string[] = [s.online ? "Online" : "Sem conexão"];
  if (s.sincronizando) partes.push("sincronizando...");
  if (s.pendentes > 0) {
    partes.push(
      s.pendentes === 1 ? "1 ação pendente de envio" : `${s.pendentes} ações pendentes de envio`
    );
  } else if (s.arquivosPendentes > 0) {
    partes.push("fotos aguardando envio");
  }
  if (s.rejeitadas > 0) {
    partes.push(s.rejeitadas === 1 ? "1 ação rejeitada" : `${s.rejeitadas} ações rejeitadas`);
  }

  let aviso: string | null = null;
  if (s.situacaoSessao === "offline_expirada") {
    aviso = "Mais de 24 h sem login com internet: novas ações bloqueadas. Conecte-se e entre novamente.";
  } else if (s.situacaoSessao === "jwt_expirado") {
    aviso = "Sessão expirada: entre novamente (com internet) para enviar as ações salvas.";
  } else if (s.erroSync && s.online) {
    aviso = `Falha no último envio: ${s.erroSync}`;
  }

  const problema = s.rejeitadas > 0 || s.situacaoSessao !== "ok";
  const corPonto = !s.online ? colors.gray[500] : problema ? colors.red[900] : colors.green[500];

  return (
    <TouchableOpacity
      activeOpacity={0.8}
      onPress={() => irParaPendencias(router)}
      style={styles.barra}
      accessibilityRole="button"
      accessibilityLabel="Ver ações pendentes e rejeitadas"
    >
      <View style={styles.linha}>
        <View style={[styles.ponto, { backgroundColor: corPonto }]} />
        <Text style={styles.texto} numberOfLines={2}>
          {partes.join(" · ")}
        </Text>
      </View>
      {aviso ? <Text style={styles.aviso}>{aviso}</Text> : null}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  barra: {
    minHeight: 36,
    paddingHorizontal: 14,
    paddingVertical: 6,
    justifyContent: "center",
    backgroundColor: colors.gray[100],
    borderBottomWidth: 1,
    borderBottomColor: colors.gray[200],
  },
  linha: { flexDirection: "row", alignItems: "center", gap: 8 },
  ponto: { width: 10, height: 10, borderRadius: 5 },
  texto: { flex: 1, fontSize: 13, color: colors.gray[800], fontWeight: "700" },
  aviso: { marginTop: 2, fontSize: 12, color: colors.red[900] },
});
