import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 14,
    backgroundColor: colors.gray[100],
  },

  title: {
    fontSize: 20,
    fontWeight: "700",
    color: colors.blue[900],
    marginBottom: 12,
  },

  loader: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
  },

  emptyContainer: {
    flexGrow: 1,
    justifyContent: "center",
    alignItems: "center",
  },

  emptyBox: {
    padding: 20,
    backgroundColor: "#fff",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.gray[200],
  },

  emptyText: {
    color: colors.gray[500],
  },
});
