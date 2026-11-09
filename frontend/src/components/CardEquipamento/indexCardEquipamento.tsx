import React from "react";
import { Text, TouchableOpacity, View } from "react-native";
import { styles } from "@/styles/styleCardEquipamento";

/** Equipamento da OS (somente leitura). Os flags vem de GET .../estado; ausentes = nao exibidos. */
export interface EquipamentoItem {
  modelo: string;
  numero_serie: string;
  foto_defeito?: boolean;
  conserto_salvo?: boolean;
  foto_conserto?: boolean;
}

interface Props {
  equip: EquipamentoItem;
  /** Sem onPress o card e apenas informativo (sem aparencia de desabilitado). */
  onPress?: () => void;
  textoAcao?: string;
}

const marca = (ok: boolean) => (ok ? "Feito" : "Pendente");

export function CardEquipamento({ equip, onPress, textoAcao }: Props) {
  const temProgresso = equip.foto_defeito !== undefined;

  const conteudo = (
    <>
      <Text style={styles.title}>{equip.modelo || "Modelo não informado"}</Text>
      <Text style={styles.text}>Número de série: {equip.numero_serie || "S/N"}</Text>

      {temProgresso ? (
        <View style={styles.progresso}>
          <Text style={styles.text}>Foto do defeito: {marca(!!equip.foto_defeito)}</Text>
          <Text style={styles.text}>Conserto salvo: {marca(!!equip.conserto_salvo)}</Text>
          <Text style={styles.text}>Foto do conserto: {marca(!!equip.foto_conserto)}</Text>
        </View>
      ) : null}

      {onPress && textoAcao ? <Text style={styles.acao}>{textoAcao}</Text> : null}
    </>
  );

  if (!onPress) return <View style={styles.card}>{conteudo}</View>;

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.8} style={styles.card}>
      {conteudo}
    </TouchableOpacity>
  );
}
