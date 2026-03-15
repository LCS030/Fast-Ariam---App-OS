import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: colors.gray[100],
  },
  title: {
    fontSize: 26,
    fontWeight: "700",
    color: colors.blue[900],
    marginBottom: 30,
    marginTop: 40,
    textAlign: "center",
  },
});
