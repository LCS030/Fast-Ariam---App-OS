/****************************************************************************************
 * FILE: src/components/input/indexInput.tsx
 ****************************************************************************************/
import React from "react";
import { View, Text, TextInput, KeyboardTypeOptions, TextInputProps } from "react-native";
import { styles } from "@/styles/styleInput";

interface Props {
  label?: string;
  placeholder?: string;
  value: string;
  onChangeText: (v: string) => void;
  secure?: boolean;
  keyboardType?: KeyboardTypeOptions;
  autoCapitalize?: TextInputProps["autoCapitalize"];
  maxLength?: number;
  editable?: boolean;
  /** Mensagem de validacao exibida junto ao campo. */
  error?: string | null;
}

export function Input({
  label,
  placeholder,
  value,
  onChangeText,
  secure,
  keyboardType,
  autoCapitalize,
  maxLength,
  editable = true,
  error,
}: Props) {
  return (
    <View style={styles.container}>
      {label && <Text style={styles.label}>{label}</Text>}
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        secureTextEntry={secure}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        maxLength={maxLength}
        editable={editable}
        style={[styles.input, error ? styles.inputError : null, !editable ? styles.inputDisabled : null]}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}
