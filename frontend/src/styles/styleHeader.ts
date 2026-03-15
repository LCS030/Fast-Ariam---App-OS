import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  container: {
    width: "100%",
    height: 100,
    paddingTop: 35,
    backgroundColor: colors.blue[900],
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 15,
  },

  actionIconContainer: {
    width: 40,
    height: 40,
    justifyContent: "center",
    alignItems: "center",
    marginLeft: 10,
  },

  logoContainer: {
    width: 140,
    height: 40,
    justifyContent: "center",
    alignItems: "flex-start",
  },

  logo: {
    width: 130,
    height: 40,
    backgroundColor: colors.gray[100],
    borderBottomRightRadius: 20,
    borderTopLeftRadius: 20,
  },
});
