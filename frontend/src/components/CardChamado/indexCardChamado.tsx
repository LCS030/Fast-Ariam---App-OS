/****************************************************************************************
 * FILE: src/components/cardChamado/indexCardChamado.tsx
 ****************************************************************************************/
import React, { useEffect, useState } from "react";
import { TouchableOpacity, View, Text, ActivityIndicator } from "react-native";
import { styles } from "../../styles/styleCardChamado";
import { formatDate } from "@/utils/formatDate";
import { router, useRouter } from "expo-router";
import api from "@/api/api";

interface Props {
  chamado: any;
}

export function CardChamado({ chamado }: Props) {
  const router = useRouter();

  return (
    <TouchableOpacity 
      style={styles.card}
      activeOpacity={0.8}
      onPress={() => router.push({
        pathname: "/detalheChamado/[id]",
        params: { id: String(chamado.id_os) },
      })}>

      <Text style={styles.nomeOs}>OS #{chamado.pedido}</Text>

      <Text style={styles.cliente}>
        {chamado.cliente_nome ?? "Cliente não informado"}
      </Text>

      <View style={styles.row}>
        <Text style={styles.statusLabel}>Status:</Text>
        <Text style={styles.statusValue}>{String(chamado.status)}</Text>
      </View>

      <Text style={styles.data}>
        Data: {formatDate(chamado.data_agendamento)}
      </Text>

    </TouchableOpacity>
  );
}
