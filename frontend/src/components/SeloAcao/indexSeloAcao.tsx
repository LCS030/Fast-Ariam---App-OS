import React from "react";
import { Text, View, StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";
import type { StatusFila } from "@/offline/tipos";

const ROTULOS: Record<StatusFila, string> = {
  pendente: "Pendente de envio",
  enviado: "Enviada",
  rejeitado: "Rejeitada",
};

const COR: Record<StatusFila, string> = {
  pendente: colors.blue[900],
  enviado: colors.green[500],
  rejeitado: colors.red[900],
};

/** Selo do estado de uma acao na fila. O texto carrega o significado (nao depende so da cor). */
export function SeloAcao({ status }: { status: StatusFila }) {
  return (
    <View style={[styles.selo, { borderColor: COR[status] }]}>
      <Text style={[styles.texto, { color: COR[status] }]}>{ROTULOS[status]}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  selo: {
    alignSelf: "flex-start",
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: "#fff",
  },
  texto: { fontSize: 12, fontWeight: "700" },
});
