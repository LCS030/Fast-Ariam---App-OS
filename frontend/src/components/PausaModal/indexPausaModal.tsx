import React, { useState } from "react";
import { Modal, View, Text, TouchableOpacity, TextInput, ScrollView } from "react-native";
import { styles as confirmStyles } from "../../styles/styleConfirmModal";

interface Props {
  visible: boolean;
  onCancel: () => void;
  onSubmit: (payload: { motivo: string; descricao?: string }) => void;
}

const REASONS = [
  "Peça pendente",
  "Cliente ausente",
  "Condições inseguras",
  "Aguardando aprovação",
  "Outro",
];

export function PausaModal({ visible, onCancel, onSubmit }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [descricao, setDescricao] = useState("");

  function handleConfirm() {
    if (!selected) return;
    const motivo = selected;
    const payload: any = { motivo };
    if (descricao && descricao.trim().length > 0) payload.descricao = descricao.trim();
    onSubmit(payload);
  }

  return (
    <Modal visible={visible} transparent animationType="fade">
      <View style={confirmStyles.overlay}>
        <View style={confirmStyles.box}>
          <Text style={confirmStyles.title}>Pausar OS</Text>
          <Text style={confirmStyles.msg}>Selecione o motivo da pausa e adicione uma descrição (opcional).</Text>

          <ScrollView style={{ maxHeight: 180, marginBottom: 12 }}>
            {REASONS.map((r) => (
              <TouchableOpacity
                key={r}
                onPress={() => setSelected(r)}
                style={{
                  paddingVertical: 10,
                  paddingHorizontal: 8,
                  borderRadius: 8,
                  marginBottom: 8,
                  backgroundColor: selected === r ? "#e6f0ff" : "#f6f6f6",
                }}
              >
                <Text style={{ fontWeight: selected === r ? "700" : "400" }}>{r}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <TextInput
            value={descricao}
            onChangeText={setDescricao}
            placeholder="Descrição (opcional)"
            style={{
              borderWidth: 1,
              borderColor: "#ddd",
              padding: 10,
              borderRadius: 8,
              marginBottom: 12,
              minHeight: 40,
            }}
            multiline
          />

          <View style={confirmStyles.row}>
            <TouchableOpacity style={confirmStyles.cancel} onPress={onCancel}>
              <Text style={confirmStyles.cancelText}>Cancelar</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={{ ...confirmStyles.ok, opacity: selected ? 1 : 0.5 }}
              onPress={handleConfirm}
              disabled={!selected}
            >
              <Text style={confirmStyles.okText}>Pausar</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

export default PausaModal;
