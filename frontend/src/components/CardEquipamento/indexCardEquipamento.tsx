import React from "react";
import { View, Text, TouchableOpacity } from "react-native";

export function CardEquipamento({ equip, disabled = false, onPress }: { equip: any; disabled?: boolean; onPress?: ()=>void }) {
  return (
    <TouchableOpacity disabled={disabled} onPress={onPress} style={{ opacity: disabled ? 0.5 : 1, padding: 10, borderWidth: 1, borderColor: "#ddd", borderRadius: 6 }}>
      <Text>Refrigerador</Text>
      <Text>Número de série: {equip.numero_serie_atendido ?? "S/N"}</Text>
    </TouchableOpacity>
  );
}