import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Alert,
  ActivityIndicator,
  Button,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { finalizarDeslocamento } from "@/api/visitas";
import { Header } from "@/components/header/indexHeader";
import { format } from "date-fns";

export default function DeslocamentoFim() {
  const params = useLocalSearchParams();
  const router = useRouter();

  const chamadoId = Number(params.chamadoId);
  const visitaId = Number(params.visitaId);
  const tipo = (params.tipo === "volta" ? "volta" : "ida") as "ida" | "volta";
  const momento = String(params.momento ?? "fim") as "inicio" | "fim";

  const [kmFim, setKmFim] = useState("");
  const [loading, setLoading] = useState(false);

  async function onFinish() {
    if (!kmFim || isNaN(Number(kmFim))) {
      Alert.alert("Erro", "Informe um KM válido.");
      return;
    }

    setLoading(true);

    try {
      await finalizarDeslocamento(
        chamadoId,
        visitaId,
        tipo,
        Number(kmFim)
      );

      Alert.alert("Sucesso", "Deslocamento finalizado!");

      // Após finalizar deslocamento → vai para upload da foto
      router.push({
        pathname: "/detalheChamado/UploadDeslocamento",
        params: {
          chamadoId,
          visitaId,
          tipo,
          momento: "fim",
        },
      });
    } catch (err: any) {
      console.log("Erro ao finalizar deslocamento:", err);
      Alert.alert("Erro", err?.response?.data?.detail || "Falha ao finalizar deslocamento.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={{ flex: 1 }}>
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />

      <View style={{ padding: 16 }}>
        <Text style={{ fontSize: 18, marginBottom: 16 }}>
          Finalizar deslocamento ({tipo})
        </Text>

        <TextInput
            placeholder="KM final"
            keyboardType="numeric"
            value={kmFim}
            onChangeText={setKmFim}
            style={{ borderWidth: 1, borderColor: "#ccc", padding: 8, marginBottom: 12 }}
        />

        <Button
          title="Finalizar deslocamento"
          onPress={onFinish}
          disabled={loading}
        />

        {loading && (
          <ActivityIndicator style={{ marginTop: 12 }} />
        )}
      </View>
    </View>
  );
}
