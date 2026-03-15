/****************************************************************************************
 * FILE: src/components/kmInput/indexKmInput.tsx
 ****************************************************************************************/
import React from "react";
import { View, Text, TextInput } from "react-native";
import { styles } from "../../styles/styleKmInput";

interface Props {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
}

export function KmInput({ label, value, onChangeText }: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>

      <TextInput
        value={value}
        onChangeText={onChangeText}
        keyboardType="numeric"
        style={styles.input}
        placeholder="0"
      />
    </View>
  );
}
