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

    // Tratamento do alerta com parser
    const detail = err?.response?.data?.detail;

    const msg = Array.isArray(detail)
        ? detail.map((d: any) => d.msg || JSON.stringify(d)).join("\n")
        : (typeof detail === "string"
            ? detail
            : JSON.stringify(detail, null, 2));

    Alert.alert("Erro", msg || "Erro desconhecido");

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
