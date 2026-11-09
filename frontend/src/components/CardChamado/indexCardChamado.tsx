/****************************************************************************************
 * FILE: src/components/CardChamado/indexCardChamado.tsx
 ****************************************************************************************/
import React from "react";
import { TouchableOpacity, View, Text } from "react-native";
import { useRouter } from "expo-router";
import { styles } from "../../styles/styleCardChamado";
import { formatDate } from "@/utils/formatDate";
import type { Chamado } from "@/api/chamado";
import { SeloAcao } from "@/components/SeloAcao/indexSeloAcao";

interface Props {
  chamado: Chamado;
  /** Acoes desta OS ainda nao confirmadas pelo servidor (RF-21). */
  pendentes?: number;
}

export function CardChamado({ chamado, pendentes = 0 }: Props) {
  const router = useRouter();

  return (
    <TouchableOpacity
      style={styles.card}
      activeOpacity={0.8}
      onPress={() =>
        router.push({
          pathname: "/detalheChamado/[id]",
          params: { id: String(chamado.id_os) },
        })
      }
    >
      <Text style={styles.nomeOs}>OS #{chamado.pedido || chamado.id_os}</Text>

      <Text style={styles.cliente}>{chamado.cliente_nome || "Cliente não informado"}</Text>

      <View style={styles.row}>
        <Text style={styles.statusLabel}>Status:</Text>
        <Text style={styles.statusValue}>{String(chamado.status)}</Text>
      </View>

      <Text style={styles.data}>Data: {formatDate(chamado.data_agendamento)}</Text>

      {pendentes > 0 ? (
        <View style={{ marginTop: 8 }}>
          <SeloAcao status="pendente" />
          <Text style={styles.data}>
            {pendentes === 1 ? "1 ação aguardando envio" : `${pendentes} ações aguardando envio`}
          </Text>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}
