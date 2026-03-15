import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  primaryBtn: {
    backgroundColor: colors.action.primary,
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: "center",
  },
  primaryText: {
    color: colors.action.text,
    fontSize: 16,
    fontWeight: "700",
  },

  secondaryBtn: {
    backgroundColor: colors.blue[900],
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: "center",
  },
  secondaryText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
});
