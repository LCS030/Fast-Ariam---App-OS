import { View, Text, TextInput, Button, Alert } from "react-native";
import { AssinaturaCanvas } from "@/components/AssinaturaCanvas/indexAssinaturaCanvas";
import { useLocalSearchParams, router } from "expo-router";
import { useState } from "react";
import api from "@/api/api";
import { Header } from "@/components/header/indexHeader";

export default function AssinaturaFinalizacao() {
  const { chamadoId, visitaId } = useLocalSearchParams();
  const [nomeCliente, setNomeCliente] = useState("");
  const [documentoCliente, setDocumentoCliente] = useState("");
  const [signature, setSignature] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function salvar() {
    if (!nomeCliente || !documentoCliente || !signature) {
      Alert.alert("Erro", "Preencha nome, documento e assine.");
      return;
    }

    try {
      setSaving(true);

      const payload = {
        nome_cliente: nomeCliente,
        documento_cliente: documentoCliente,
        assinatura_base64: signature,
      };

      await api.post(
        `/chamados/${chamadoId}/visitas/${visitaId}/finalizar-atendimento`,
        payload
      );

      Alert.alert("Sucesso", "Atendimento finalizado!");
      router.replace(`/detalheChamado/${chamadoId}`);
    } catch (error) {
      console.log(error);
      Alert.alert("Erro", "Falha ao finalizar atendimento");
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={{flex: 1}}>
        <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />
        <View style={{ padding: 16 }}>
            <Text style={{ fontWeight: "bold", fontSize: 18, marginBottom: 10 }}>
                Dados do Cliente
            </Text>

            <Text>Nome</Text>
            <TextInput
                value={nomeCliente}
                onChangeText={setNomeCliente}
                placeholder="Nome do cliente"
                style={{ borderWidth: 1, borderRadius: 6, padding: 8, marginBottom: 12 }}
            />

            <Text>Documento (CPF/CNPJ)</Text>
            <TextInput
                value={documentoCliente}
                onChangeText={setDocumentoCliente}
                placeholder="Documento"
                style={{ borderWidth: 1, borderRadius: 6, padding: 8, marginBottom: 20 }}
            />

            <AssinaturaCanvas onOK={setSignature} />

            <Button title={saving ? "Enviando..." : "Finalizar Atendimento"} onPress={salvar} />
        </View>
    </View>
    
  );
}
