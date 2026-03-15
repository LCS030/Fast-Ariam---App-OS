/****************************************************************************************
 * FILE: src/components/cardChamado/styleCardChamado.ts
 ****************************************************************************************/
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: colors.gray[200],
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  cliente: {
    fontSize: 18,
    fontWeight: "700",
    color: colors.blue[900],
    marginBottom: 4,
  },
  descricao: {
    fontSize: 14,
    color: colors.gray[500],
    marginBottom: 12,
  },
  row: {
    flexDirection: "row",
    marginBottom: 8,
  },
  statusLabel: {
    fontWeight: "700",
    marginRight: 6,
    color: colors.gray[800],
  },
  statusValue: {
    color: colors.blue[900],
  },
  data: {
    fontSize: 12,
    color: colors.gray[400],
    marginTop: 4,
  },
  nomeOs: {
  fontSize: 16,
  fontWeight: "bold",
  marginBottom: 4,
  color: colors.blue[900]
},


});
