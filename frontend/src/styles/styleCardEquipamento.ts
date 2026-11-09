/****************************************************************************************
 * FILE: src/components/cardEquipamento/styleCardEquipamento.ts
 ****************************************************************************************/
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  container: {
    backgroundColor: "#eeeeeeff"
  },
  card: {
    backgroundColor: "#fff",
    borderRadius: 10,
    padding: 12,
    minHeight: 56,
    borderWidth: 1,
    borderColor: colors.gray[200],
  },
  title: {
    color: colors.blue[900],
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 8,
  },
  text: {
    fontSize: 14,
    color: colors.gray[800],
  },
  progresso: {
    marginTop: 8,
    gap: 2,
  },
  acao: {
    marginTop: 10,
    fontSize: 14,
    fontWeight: "700",
    color: colors.blue[900],
  },
});
