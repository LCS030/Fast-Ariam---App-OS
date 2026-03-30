/****************************************************************************************
 * FILE: src/components/fotoInput/indexFotoInput.tsx
 ****************************************************************************************/
import React from "react";
import { View, Text, TouchableOpacity, Image, Alert, ActivityIndicator } from "react-native";
import { styles } from "../../styles/styleFotoInput";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import * as FileSystem from "expo-file-system/legacy";

interface Props {
  label: string;
  value?: string | null;
  onCapture: (uri: string) => void;
  type?: "defeito" | "conserto"; // Tipo de foto para feedback customizado
}

const MIN_WIDTH = 960;
const MIN_HEIGHT = 1280;

export function FotoInput({ label, value, onCapture, type }: Props) {
  const [loading, setLoading] = React.useState(false);

  /**
   * Lê as dimensões da imagem usando FileSystem
   */
  async function getImageDimensions(uri: string): Promise<{ width: number; height: number } | null> {
    try {
      const base64 = await FileSystem.readAsStringAsync(uri, {
        encoding: "base64",
      });

      // Decodificar base64 para buffer (primitivo)
      const binaryString = atob(base64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Verificar se é JPEG (FF D8 FF) ou PNG (89 50 4E 47)
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
          // SOF0, SOF1, SOF2 contêm altura e largura
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
    // PNG width/height estão nos bytes 16-24 (big-endian)
    const width = (bytes[16] << 24) | (bytes[17] << 16) | (bytes[18] << 8) | bytes[19];
    const height = (bytes[20] << 24) | (bytes[21] << 16) | (bytes[22] << 8) | bytes[23];
    return { width, height };
  }

  async function handleTakePhoto() {
    try {
      setLoading(true);
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        Alert.alert("Permissão", "Acesso à câmera é necessário.");
        return;
      }

      const result = await ImagePicker.launchCameraAsync({
        quality: 0.7, // Compressão otimizada para dados móveis
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
          const typeLabel = type === "defeito" ? "defeito" : "conserto";
          Alert.alert(
            "Resolução insuficiente",
            `A foto de ${typeLabel} deve ter no mínimo ${MIN_WIDTH}x${MIN_HEIGHT}.\nSua foto: ${dimensions.width}x${dimensions.height}`
          );
          return;
        }

        onCapture(uri);
      }
    } catch (error) {
      console.error("Erro ao capturar foto:", error);
      Alert.alert("Erro", "Falha ao capturar foto. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>

      <TouchableOpacity style={styles.box} onPress={handleTakePhoto} disabled={loading}>
        {loading ? (
          <ActivityIndicator size="large" color="#0066cc" />
        ) : value ? (
          <Image source={{ uri: value }} style={styles.preview} />
        ) : (
          <Ionicons name="camera" size={32} color="#888" />
        )}
      </TouchableOpacity>
    </View>
  );
}
