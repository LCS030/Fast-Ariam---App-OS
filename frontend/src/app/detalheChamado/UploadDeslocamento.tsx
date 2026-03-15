// src/app/detalheChamado/UploadDeslocamento.tsx
import React, { useEffect, useState } from "react";
import { View, Text, Button, Image, Alert, ActivityIndicator } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams, useRouter } from "expo-router";
import { uploadDeslocamento } from "@/api/visitas";
import { Header } from "@/components/header/indexHeader"

export default function UploadDeslocamentoScreen() {
  const params = useLocalSearchParams();
  const router = useRouter();
  const chamadoId = Number(params.chamadoId);
  const visitaId = Number(params.visitaId);
  const tipo = String(params.tipo) as "ida" | "volta";
  const momento = String(params.momento) as "inicio" | "fim";

    console.log("PARAMS ===>", params);
console.log("Momento ===>", momento);
console.log("Tipo ===>", tipo);

  const [image, setImage] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== "granted") {
        Alert.alert("Permissão", "Permissão de câmera necessária.");
      }
    })();
  }, []);

  async function takePhoto() {
  const result = await ImagePicker.launchCameraAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    quality: 0.7,
  });

    if (!result.canceled) {
        setImage(result.assets[0]);  // <-- CORRETO
    }
}

  async function onUpload() {
    if (!image) { Alert.alert("Erro", "Tire a foto antes de enviar."); return; }
    setLoading(true);
    try {
      await uploadDeslocamento(
            chamadoId,
            visitaId,
            image.uri,   // agora existe
            "image/jpeg",
            tipo,
            momento
        );
      Alert.alert("Ok", "Foto enviada com sucesso.");
      router.replace(`/detalheChamado/${chamadoId}`);
    } catch (err: any) {
      console.log("Erro upload", err);
      Alert.alert("Erro", err?.response?.data?.detail || "Falha ao enviar foto.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={{flex:1}}>

        <Header leftIconName={null} />
            
        <View style={{ flex:1, padding: 16 }}>
        <Text style={{ fontSize: 18 }}>Tire a foto do hôdometro</Text>
        {image ? (
            <Image source={{ uri: image.uri }} style={{ width: "100%", height: 300, marginTop: 12 }} />
        ) : (
            <View style={{ height: 600, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#ccc", marginTop: 12 }}>
            <Text>Sem foto</Text>
            </View>
        )}

        <Button title="Tirar foto" onPress={takePhoto} />
        <View style={{ height: 8 }} />
        <Button title="Enviar foto" onPress={onUpload} disabled={loading || !image} />
        {loading && <ActivityIndicator style={{ marginTop: 12 }} />}
        </View>
    </View>
  );
}
