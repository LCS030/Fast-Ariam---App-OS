/****************************************************************************************
 * FILE: src/components/cardVisita/styleCardVisita.ts
 ****************************************************************************************/
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.gray[200],
  },
  title: {
    fontWeight: "700",
    fontSize: 15,
    color: colors.blue[900],
    marginBottom: 6,
  },
  text: {
    fontSize: 14,
    color: colors.gray[800],
  },
});
