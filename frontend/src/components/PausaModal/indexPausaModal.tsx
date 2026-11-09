import React, { useEffect, useState } from "react";
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  TextInput,
  ScrollView,
  ActivityIndicator,
} from "react-native";
import { styles as confirmStyles } from "../../styles/styleConfirmModal";
import { colors } from "@/styles/Colors";
import { getErrorMessage } from "@/utils/alerts";
import { MOTIVOS_PAUSA, MOTIVO_OUTRO, validarPausa } from "@/utils/pausa";

interface Props {
  visible: boolean;
  onCancel: () => void;
  /** Deve rejeitar (throw) se a API recusar; a mensagem e exibida no proprio modal. */
  onSubmit: (payload: { motivo: string; descricao?: string }) => Promise<void>;
}

export function PausaModal({ visible, onCancel, onSubmit }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [descricao, setDescricao] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  // Cada abertura comeca limpa.
  useEffect(() => {
    if (visible) {
      setSelected(null);
      setDescricao("");
      setErro(null);
      setEnviando(false);
    }
  }, [visible]);

  async function handleConfirm() {
    if (enviando) return;

    const invalido = validarPausa(selected, descricao);
    if (invalido) {
      setErro(invalido);
      return;
    }

    const texto = descricao.trim();
    setErro(null);
    setEnviando(true);
    try {
      await onSubmit({ motivo: selected as string, descricao: texto || undefined });
    } catch (err) {
      setErro(getErrorMessage(err, "Falha ao registrar a pausa."));
    } finally {
      setEnviando(false);
    }
  }

  const outro = selected === MOTIVO_OUTRO;

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={confirmStyles.overlay}>
        <View style={confirmStyles.box}>
          <Text style={confirmStyles.title}>Pausar OS</Text>
          <Text style={confirmStyles.msg}>
            Selecione o motivo da pausa. Depois de pausar, o atendimento não poderá ser finalizado
            nesta visita: você volta ao ponto de partida e o administrador faz o reagendamento.
          </Text>

          <ScrollView style={{ maxHeight: 240, marginBottom: 12 }}>
            {MOTIVOS_PAUSA.map((r) => (
              <TouchableOpacity
                key={r}
                onPress={() => {
                  setSelected(r);
                  setErro(null);
                }}
                disabled={enviando}
                accessibilityRole="radio"
                accessibilityState={{ selected: selected === r }}
                style={{
                  minHeight: 48,
                  justifyContent: "center",
                  paddingHorizontal: 12,
                  borderRadius: 8,
                  marginBottom: 8,
                  borderWidth: 1,
                  borderColor: selected === r ? colors.action.primary : colors.gray[200],
                  backgroundColor: selected === r ? "#e6f0ff" : colors.gray[100],
                }}
              >
                <Text
                  style={{
                    fontSize: 15,
                    color: colors.gray[950],
                    fontWeight: selected === r ? "700" : "400",
                  }}
                >
                  {r}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <TextInput
            value={descricao}
            onChangeText={(t) => {
              setDescricao(t);
              setErro(null);
            }}
            editable={!enviando}
            placeholder={outro ? "Descrição (obrigatória)" : "Descrição (opcional)"}
            style={{
              borderWidth: 1,
              borderColor: colors.gray[200],
              padding: 10,
              borderRadius: 8,
              marginBottom: 8,
              minHeight: 64,
              textAlignVertical: "top",
              fontSize: 15,
            }}
            multiline
          />

          {erro ? (
            <Text style={{ color: colors.red[900], fontSize: 13, marginBottom: 8 }}>{erro}</Text>
          ) : null}

          <View style={confirmStyles.row}>
            <TouchableOpacity
              style={[confirmStyles.cancel, { minHeight: 44, justifyContent: "center" }]}
              onPress={onCancel}
              disabled={enviando}
            >
              <Text style={confirmStyles.cancelText}>Cancelar</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                confirmStyles.ok,
                { minHeight: 44, justifyContent: "center", opacity: enviando ? 0.6 : 1 },
              ]}
              onPress={handleConfirm}
              disabled={enviando}
            >
              {enviando ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={confirmStyles.okText}>Pausar</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

export default PausaModal;
