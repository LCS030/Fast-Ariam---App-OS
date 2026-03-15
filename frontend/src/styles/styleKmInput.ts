/****************************************************************************************
 * FILE: src/components/kmInput/styleKmInput.ts
 ****************************************************************************************/
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  container: { marginBottom: 16 },
  label: {
    marginBottom: 6,
    fontSize: 15,
    fontWeight: "600",
    color: colors.gray[800],
  },
  input: {
    height: 46,
    borderRadius: 8,
    paddingHorizontal: 12,
    backgroundColor: colors.gray[100],
    borderWidth: 1,
    borderColor: colors.gray[200],
    fontSize: 16,
  },
});
