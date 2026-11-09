/****************************************************************************************
 * FILE: src/components/input/styleInput.ts
 ****************************************************************************************/
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  container: { marginBottom: 16 },
  label: {
    color: colors.gray[800],
    fontSize: 14,
    marginBottom: 6,
  },
  input: {
    height: 48,
    borderRadius: 8,
    paddingHorizontal: 12,
    backgroundColor: colors.gray[100],
    borderWidth: 1,
    borderColor: colors.gray[200],
    fontSize: 16,
    color: colors.gray[950],
  },
  inputError: {
    borderColor: colors.red[500],
  },
  inputDisabled: {
    opacity: 0.6,
  },
  error: {
    marginTop: 4,
    fontSize: 13,
    color: colors.red[900],
  },
});
