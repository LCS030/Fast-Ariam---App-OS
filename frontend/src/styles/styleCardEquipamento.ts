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
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.gray[200],
  },
  title: {
    color: colors.blue[900],
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 8,
  },
  line: {
    padding: 20,
    fontSize: 14,
    color: colors.gray[800],
  },
});
