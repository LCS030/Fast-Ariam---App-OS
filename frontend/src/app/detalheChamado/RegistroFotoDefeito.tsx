import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Image,
  Alert,
  ActivityIndicator,
  ScrollView,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as FileSystem from "expo-file-system/legacy";
import { useLocalSearchParams, useRouter } from "expo-router";
import { uploadFotoDefeito } from "@/api/chamado";
import { Header } from "@/components/header/indexHeader";
import { Button } from "@/components/button/indexButton";
import { alertError } from "@/utils/alerts";
import { StyleSheet } from "react-native";
import { colors } from "@/styles/Colors";

const MIN_WIDTH = 960;
const MIN_HEIGHT = 1280;

export default function RegistroFotoDefeitoScreen() {
  const params = useLocalSearchParams();
  const router = useRouter();

  const chamadoId = Number(params.chamadoId);
  const visitaId = Number(params.visitaId);
  const servicoId = Number(params.servicoId);

  const [imageUri, setImageUri] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    console.log("RegistroFotoDefeito params:", { chamadoId, visitaId, servicoId, params });
  }, [chamadoId, visitaId, servicoId, params]);

  useEffect(() => {
    (async () => {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== "granted") {
        Alert.alert("Permissão", "Permissão de câmera necessária.");
      }
    })();
  }, []);

  /**
   * Lê as dimensões da imagem usando FileSystem
   */
  async function getImageDimensions(uri: string): Promise<{ width: number; height: number } | null> {
    try {
      const base64 = await FileSystem.readAsStringAsync(uri, {
        encoding: "base64",
      });

      const binaryString = atob(base64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const isJpeg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
      const isPng = bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47;

      if (isJpeg) {
        return parseJpegDimensions(bytes);
      } else if (isPng) {
        return parsePngDimensions(bytes);
      }
      return null;
    } catch (error) {
      console.log("Erro ao ler dimensões:", error);
      return null;
    }
  }

  function parseJpegDimensions(bytes: Uint8Array): { width: number; height: number } | null {
    let offset = 2;
    while (offset < bytes.length) {
      if (bytes[offset] === 0xff) {
        const marker = bytes[offset + 1];
        if (marker === 0xc0 || marker === 0xc1 || marker === 0xc2) {
          const height = (bytes[offset + 5] << 8) | bytes[offset + 6];
          const width = (bytes[offset + 7] << 8) | bytes[offset + 8];
          return { width, height };
        }
        const segmentLength = (bytes[offset + 2] << 8) | bytes[offset + 3];
        offset += segmentLength + 2;
      } else {
        offset++;
      }
    }
    return null;
  }

  function parsePngDimensions(bytes: Uint8Array): { width: number; height: number } | null {
    if (bytes.length < 24) return null;
    const width = (bytes[16] << 24) | (bytes[17] << 16) | (bytes[18] << 8) | bytes[19];
    const height = (bytes[20] << 24) | (bytes[21] << 16) | (bytes[22] << 8) | bytes[23];
    return { width, height };
  }

  async function takePhoto() {
    try {
      setLoading(true);
      const result = await ImagePicker.launchCameraAsync({
        quality: 0.7,
      });

      if (!result.canceled) {
        const uri = result.assets[0].uri;

        // Validar resolução
        const dimensions = await getImageDimensions(uri);
        if (!dimensions) {
          Alert.alert("Erro", "Não foi possível ler as dimensões da imagem. Tente novamente.");
          return;
        }

        if (dimensions.width < MIN_WIDTH || dimensions.height < MIN_HEIGHT) {
          Alert.alert(
            "Resolução insuficiente",
            `Mínimo requerido: ${MIN_WIDTH}x${MIN_HEIGHT}.\nSua foto: ${dimensions.width}x${dimensions.height}`
          );
          return;
        }

        setImageUri(uri);
      }
    } catch (error) {
      console.error("Erro ao capturar foto:", error);
      Alert.alert("Erro", "Falha ao capturar foto.");
    } finally {
      setLoading(false);
    }
  }

  async function onUpload() {
    if (!imageUri) {
      Alert.alert("Erro", "Tire a foto do defeito antes de enviar.");
      return;
    }

    setUploading(true);
    try {
      await uploadFotoDefeito(chamadoId, visitaId, servicoId, imageUri);
      Alert.alert("Sucesso", "Foto do defeito enviada com sucesso!");
      router.replace(`/detalheChamado/${chamadoId}`);
    } catch (err: any) {
      console.log("Erro upload", err);
      alertError(err, "Falha ao enviar foto do defeito.");
    } finally {
      setUploading(false);
    }
  }

  function handleDiscard() {
    setImageUri(null);
  }

  return (
    <View style={{ flex: 1, backgroundColor: "#fff" }}>
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />

      <ScrollView style={styles.container}>
        <View style={{ marginTop: 20, marginBottom: 20 }}>
          <Text style={styles.title}>Foto do Defeito</Text>
          <Text style={styles.subtitle}>
            Tire uma foto do equipamento com o defeito antes de iniciar o reparo
          </Text>
        </View>

        {/* Foto preview */}
        <View style={styles.imageContainer}>
          {imageUri ? (
            <Image source={{ uri: imageUri }} style={styles.image} />
          ) : loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={colors.blue[900]} />
              <Text style={styles.loadingText}>Capturando foto...</Text>
            </View>
          ) : (
            <View style={styles.placeholderContainer}>
              <Text style={styles.placeholderText}>Nenhuma foto capturada</Text>
            </View>
          )}
        </View>

        {/* Botões */}
        <View style={{ marginTop: 20, gap: 12 }}>
          <Button
            title={imageUri ? "Tirar Nova Foto" : "Tirar Foto"}
            onPress={takePhoto}
            width="100%"
            disabled={loading || uploading}
          />

          {imageUri && (
            <>
              <Button
                title="Descartar Foto"
                onPress={handleDiscard}
                width="100%"
                disabled={uploading}
              />
              <Button
                title={uploading ? "Enviando..." : "Confirmar e Enviar"}
                onPress={onUpload}
                width="100%"
                disabled={uploading}
              />
            </>
          )}
        </View>

        <View style={{ height: 20 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: "700",
    color: colors.blue[900],
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: colors.gray[500],
    lineHeight: 20,
  },
  imageContainer: {
    width: "100%",
    height: 300,
    backgroundColor: colors.gray[100],
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 2,
    borderColor: colors.gray[200],
    justifyContent: "center",
    alignItems: "center",
  },
  image: {
    width: "100%",
    height: "100%",
  },
  loadingContainer: {
    justifyContent: "center",
    alignItems: "center",
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: colors.gray[500],
  },
  placeholderContainer: {
    justifyContent: "center",
    alignItems: "center",
  },
  placeholderText: {
    fontSize: 16,
    color: colors.gray[400],
  },
});
