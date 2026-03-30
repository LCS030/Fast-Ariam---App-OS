import React, { useState } from "react";
import { View, Text, TextInput, Button, Alert, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { iniciarDeslocamento } from "@/api/visitas";
import { format } from "date-fns";
import { Header } from "@/components/header/indexHeader";
import { formatError } from "@/utils/alerts";



export default function DeslocamentoInicioScreen() {
    
  const params = useLocalSearchParams();
  const router = useRouter();

  const tipo = (params.tipo === "volta" ? "volta" : "ida") as "ida" | "volta";
  const momento = String(params.momento ?? "inicio") as "inicio" | "fim";

  // Normalização do param
  const rawChamado = params.chamadoId;
  const rawVisita = params.visitaId;
  

  const chamadoId = Number(Array.isArray(rawChamado) ? rawChamado[0] : rawChamado);
  const visitaId = Number(Array.isArray(rawVisita) ? rawVisita[0] : rawVisita);

  const [km, setKm] = useState("");
  const [loading, setLoading] = useState(false);

  async function onStart() {
  

  if (!km || isNaN(Number(km))) {
    Alert.alert("Erro", "Informe um KM válido.");
    return;
  }

  setLoading(true);

  try {
    await iniciarDeslocamento(chamadoId, visitaId, {
      tipo: tipo,
      km_inicio: Number(km)
    });

    Alert.alert("Sucesso", "Deslocamento iniciado!");

        router.push({
        pathname: "/detalheChamado/UploadDeslocamento",
        params: {
            chamadoId,
            visitaId,
            tipo,
            momento: "inicio"
        },
    });

  } catch (err: any) {
    console.error("DEBUG iniciarDeslocamento ERROR:", {
      status: err?.response?.status,
      data: err?.response?.data,
      detail: err?.response?.data?.detail,
      message: err?.message,
      full: err
    });

    // Tratamento do alerta com parser
    const detail = err?.response?.data?.detail;

    let msg = "Erro desconhecido";
    
    if (Array.isArray(detail)) {
      msg = detail.map((d: any) => d.msg || JSON.stringify(d)).join("\n");
    } else if (typeof detail === "string") {
      msg = detail;
    } else if (err?.response?.status === 403) {
      msg = "Acesso negado. Verifique se você está logado como técnico.";
    } else if (err?.response?.status === 404) {
      msg = "Chamado ou visita não encontrados.";
    } else if (err?.response?.status === 400) {
      msg = detail || "Dados inválidos enviados.";
    } else if (err?.message) {
      msg = err.message;
    }

    Alert.alert("Erro", msg);

    } finally {
    setLoading(false);
    }}



  return (
    <View style={{flex: 1}}>

        <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />

        <View style={{ flex: 1, padding: 16 }}>
        <Text style={{ fontSize: 18, marginBottom: 8 }}>Iniciar deslocamento</Text>

        <TextInput
            placeholder="KM inicial"
            keyboardType="numeric"
            value={km}
            onChangeText={setKm}
            style={{ borderWidth: 1, borderColor: "#ccc", padding: 8, marginBottom: 12 }}
        />

        <Button title="Iniciar deslocamento" onPress={onStart} disabled={loading} />
        {loading && <ActivityIndicator style={{ marginTop: 12 }} />}
        </View>
    </View>
  );
}
