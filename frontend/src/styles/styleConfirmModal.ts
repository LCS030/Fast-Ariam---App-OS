/****************************************************************************************
 * FILE: src/components/confirmModal/styleConfirmModal.ts
 ****************************************************************************************/
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "#0008",
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 20,
  },
  box: {
    width: "100%",
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 20,
  },
  title: {
    fontSize: 18,
    fontWeight: "700",
    color: colors.gray[950],
    marginBottom: 10,
  },
  msg: {
    fontSize: 14,
    color: colors.gray[800],
    marginBottom: 20,
  },
  row: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 12,
  },
  cancel: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    backgroundColor: colors.gray[200],
    borderRadius: 8,
  },
  cancelText: {
    fontWeight: "700",
    color: colors.gray[800],
  },
  ok: {
    paddingVertical: 10,
    paddingHorizontal: 18,
    backgroundColor: colors.action.primary,
    borderRadius: 8,
  },
  okText: {
    fontWeight: "700",
    color: "#fff",
  },
});
