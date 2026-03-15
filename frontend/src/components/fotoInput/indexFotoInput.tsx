/****************************************************************************************
 * FILE: src/components/fotoInput/indexFotoInput.tsx
 ****************************************************************************************/
import React from "react";
import { View, Text, TouchableOpacity, Image } from "react-native";
import { styles } from "../../styles/styleFotoInput";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";

interface Props {
  label: string;
  value?: string | null;
  onCapture: (uri: string) => void;
}

export function FotoInput({ label, value, onCapture }: Props) {
  async function handleTakePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return;

    const result = await ImagePicker.launchCameraAsync({
      quality: 0.6,
    });

    if (!result.canceled) {
      onCapture(result.assets[0].uri);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>

      <TouchableOpacity style={styles.box} onPress={handleTakePhoto}>
        {value ? (
          <Image source={{ uri: value }} style={styles.preview} />
        ) : (
          <Ionicons name="camera" size={32} color="#888" />
        )}
      </TouchableOpacity>
    </View>
  );
}
