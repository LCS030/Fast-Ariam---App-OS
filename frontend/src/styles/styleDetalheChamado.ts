// File: src/styles/styleDetalheChamado.ts
import { StyleSheet, Platform } from "react-native";
import { colors } from "./Colors";

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
    paddingHorizontal: 14,
  },

  loader: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
  },

  top: {
    marginTop: 10,
    marginBottom: 8,
  },

  osTitle: {
    fontSize: 22,
    fontWeight: "700",
    color: colors.blue[900],
    marginBottom: 6,
  },

  descricao: {
    fontSize: 15,
    color: colors.gray[500],
    marginBottom: 8,
  },

  status: {
    fontSize: 15,
    marginBottom: 12,
    color: colors.gray[800],
  },

  section: {
    marginTop: 14,
    marginBottom: 6,
  },

  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.blue[900],
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 6,
  },

  sectionTitle: {
    color: colors.blue[900],
    fontWeight: "700",
    fontSize: 20,
  },

  clienteTitle: {
    color: colors.gray[950],
    paddingTop: 10,
    paddingBottom: 20,
    fontWeight: "500",
    fontSize: 16,
  },

  headerSmallBtn: {
    backgroundColor: colors.gray[100],
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 6,
  },

  headerSmallBtnText: {
    color: colors.blue[900],
    fontWeight: "700",
    fontSize: 12,
  },

  equipList: {
    marginTop: 12,
  },

  equipCardWrapper: {
    marginBottom: 12,
  },

  emptyEquip: {
    padding: 12,
    backgroundColor: "#fff",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.gray[200],
    marginTop: 12,
  },

  emptyEquipText: {
    color: colors.gray[500],
  },

  clientCard: {
    marginTop: 12,
    padding: 12,
    backgroundColor: "#fff",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.gray[200],
  },

  clientLabel: {
    fontSize: 13,
    color: colors.gray[800],
    fontWeight: "700",
    marginBottom: 6,
  },

  clientAddress: {
    fontSize: 14,
    color: colors.gray[800],
    marginBottom: 4,
  },

  mapContainer: {
    marginTop: 10,
    height: 200,
    borderRadius: 8,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.gray[200],
  },

  map: {
    ...Platform.select({
      ios: { flex: 1 },
      android: { flex: 1 },
    }),
  },
});
