/****************************************************************************************
 * FILE: src/components/fotoInput/styleFotoInput.ts
 ****************************************************************************************/
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  container: { marginBottom: 20 },
  label: {
    marginBottom: 6,
    fontSize: 15,
    fontWeight: "600",
    color: colors.gray[800],
  },
  box: {
    height: 140,
    borderRadius: 12,
    backgroundColor: colors.gray[100],
    borderWidth: 1,
    borderColor: colors.gray[200],
    justifyContent: "center",
    alignItems: "center",
    overflow: "hidden",
  },
  preview: { width: "100%", height: "100%" },
});
