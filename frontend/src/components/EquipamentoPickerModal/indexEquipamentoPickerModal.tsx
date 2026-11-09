import React from "react";
import { Modal, View, Text, TouchableOpacity, ScrollView } from "react-native";
import { styles as confirmStyles } from "../../styles/styleConfirmModal";
import { colors } from "@/styles/Colors";
import type { EquipamentoEstado } from "@/api/visitas";

interface Props {
  visible: boolean;
  titulo: string;
  /** Qual foto esta sendo registrada: define o indicador "foto ja registrada". */
  tipo: "defeito" | "conserto";
  equipamentos: EquipamentoEstado[];
  onSelect: (equip: EquipamentoEstado) => void;
  onCancel: () => void;
}

/** Escolha do equipamento (da OS, somente leitura) ao qual a foto sera associada. */
export function EquipamentoPickerModal({
  visible,
  titulo,
  tipo,
  equipamentos,
  onSelect,
  onCancel,
}: Props) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={confirmStyles.overlay}>
        <View style={confirmStyles.box}>
          <Text style={confirmStyles.title}>{titulo}</Text>
          <Text style={confirmStyles.msg}>Selecione o equipamento desta foto.</Text>

          <ScrollView style={{ maxHeight: 280, marginBottom: 12 }}>
            {equipamentos.map((e) => {
              const registrada = tipo === "defeito" ? e.foto_defeito : e.foto_conserto;
              return (
                <TouchableOpacity
                  key={e.id_servico}
                  onPress={() => onSelect(e)}
                  style={{
                    minHeight: 52,
                    justifyContent: "center",
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    borderRadius: 8,
                    marginBottom: 8,
                    borderWidth: 1,
                    borderColor: colors.gray[200],
                    backgroundColor: colors.gray[100],
                  }}
                >
                  <Text style={{ fontWeight: "700", color: colors.blue[900] }}>{e.modelo}</Text>
                  <Text style={{ color: colors.gray[800] }}>Série: {e.numero_serie || "S/N"}</Text>
                  <Text style={{ color: colors.gray[800] }}>
                    Foto: {registrada ? "já registrada" : "pendente"}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <View style={confirmStyles.row}>
            <TouchableOpacity
              style={[confirmStyles.cancel, { minHeight: 44, justifyContent: "center" }]}
              onPress={onCancel}
            >
              <Text style={confirmStyles.cancelText}>Cancelar</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}
