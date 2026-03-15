/****************************************************************************************
 * FILE: src/components/cardVisita/indexCardVisita.tsx
 ****************************************************************************************/
import React from "react";
import { View, Text } from "react-native";
import { styles } from "../../styles/styleCardVisita";
import { colors } from "@/styles/Colors";

export function CardVisita({ visita }: { visita: any }) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>Visita #{visita.id}</Text>
      <Text style={styles.text}>Status: {visita.servico_finalizado ? "Finalizada" : "Em andamento"}</Text>
      <Text style={styles.text}>KM Total: {visita.km_total ?? "-"}</Text>
    </View>
  );
}
