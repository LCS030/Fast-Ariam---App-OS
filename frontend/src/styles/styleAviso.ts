import { StyleSheet } from "react-native";
import { colors } from "./Colors";

/** Mesmo padrao visual do avisoBox da tela de detalhe da OS, para reuso em outras telas. */
export const styleAviso = StyleSheet.create({
  box: {
    marginTop: 8,
    marginBottom: 12,
    padding: 12,
    backgroundColor: colors.gray[100],
    borderRadius: 8,
    borderLeftWidth: 4,
    borderLeftColor: colors.blue[900],
  },
  boxErro: {
    marginTop: 8,
    marginBottom: 12,
    padding: 12,
    backgroundColor: colors.gray[100],
    borderRadius: 8,
    borderLeftWidth: 4,
    borderLeftColor: colors.red[900],
  },
  titulo: {
    color: colors.blue[900],
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 4,
  },
  texto: {
    color: colors.gray[800],
    fontSize: 14,
  },
});
