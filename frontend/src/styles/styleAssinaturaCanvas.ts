// File: src/components/assinaturaCanvas/styleAssinaturaCanvas.ts
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

export const styles = StyleSheet.create({
  container: { marginVertical: 20, paddingHorizontal: 12 },
  label: {
    fontSize: 15,
    fontWeight: "700",
    color: colors.gray[800],
    marginBottom: 8,
  },
  box: {
    height: 260,
    borderWidth: 1,
    borderColor: colors.gray[200],
    borderRadius: 12,
    overflow: "hidden",
    backgroundColor: "#fff",
  },

  // botão limpar (já tinha)
  btnClear: {
    alignSelf: "flex-end",
    marginTop: 10,
    backgroundColor: colors.red[500],
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
  },
  btnClearText: {
    color: "#fff",
    fontWeight: "700",
  },

  // novo: botão salvar assinatura (primário)
  btnSave: {
    alignSelf: "flex-end",
    marginTop: 12,
    backgroundColor: colors.action.primary,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
  },
  btnSaveText: {
    color: colors.action.text,
    fontWeight: "700",
    fontSize: 14,
  },

});

export const webStyle = `
  .m-signature-pad--footer { display: none; margin: 0px; }
  .m-signature-pad { box-shadow: none; border: none; }
`
