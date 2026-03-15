/****************************************************************************************
 * FILE: src/components/input/indexInput.tsx
 ****************************************************************************************/
import React from "react";
import { View, Text, TextInput } from "react-native";
import { styles } from "@/styles/styleInput";

interface Props {
  label?: string;
  placeholder?: string;
  value: string;
  onChangeText: (v: string) => void;
  secure?: boolean;
  keyboardType?: any;
}

export function Input({ label, placeholder, value, onChangeText, secure, keyboardType }: Props) {
  return (
    <View style={styles.container}>
      {label && <Text style={styles.label}>{label}</Text>}
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        secureTextEntry={secure}
        keyboardType={keyboardType}
        style={styles.input}
      />
    </View>
  );
}
