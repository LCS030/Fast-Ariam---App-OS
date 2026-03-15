// File: src/app/detalheChamado/[id].tsx
import React, { useEffect, useState, useMemo, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import MapView, { Marker, PROVIDER_GOOGLE } from "react-native-maps";

import { Header } from "@/components/header/indexHeader";
import { CardEquipamento } from "@/components/CardEquipamento/indexCardEquipamento";
import { concluirChamado, getChamadoPorId } from "@/api/chamado";
import { enviarAssinatura, getEstadoVisita, iniciarAtendimentoVisita } from "@/api/visitas";
import { Button } from "@/components/button/indexButton";
import { alertError } from "@/utils/alerts";
import { styles } from "@/styles/styleDetalheChamado";
import { colors } from "@/styles/Colors";
import { format } from "date-fns";

const DEFAULT_REGION = {
  latitude: -23.55052,
  longitude: -46.633308,
  latitudeDelta: 0.05,
  longitudeDelta: 0.05,
};

export default function DetalheChamadoScreen() {
  const params = useLocalSearchParams();
  const router = useRouter();

  const idNum = Number(params.id);

  const [chamado, setChamado] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  const [estado, setEstado] = useState<any | null>(null);
  const [loadingEstado, setLoadingEstado] = useState(true);

  const loadChamado = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getChamadoPorId(idNum);
      setChamado(data);
    } catch (err) {
      alertError(err, "Falha ao carregar o chamado.");
    } finally {
      setLoading(false);
    }
  }, [idNum]);

  const loadEstado = useCallback(async (id_visita: number) => {
    try {
      setLoadingEstado(true);
      const est = await getEstadoVisita(idNum, id_visita);
      setEstado(est);
    } catch (err) {
      console.log("Erro ao carregar estado da visita", err);
    } finally {
      setLoadingEstado(false);
    }
  }, [idNum]);

  useEffect(() => {
    if (!Number.isFinite(idNum) || idNum <= 0) {
      Alert.alert("ID inválido", "ID do chamado inválido.");
      return;
    }
    loadChamado();
  }, [loadChamado]);

  useEffect(() => {
    if (chamado?.visitas?.length > 0) {
      const visita = chamado.visitas[0];
      loadEstado(visita.id_visita);
    }
  }, [chamado]);

  const equipamentos = useMemo(() => {
    if (!chamado) return [];
    const visitas = chamado.visitas || [];
    const arr: any[] = [];
    visitas.forEach((v: any) => {
      if (Array.isArray(v.servicos_realizados)) {
        arr.push(...v.servicos_realizados);
      }
    });
    return arr;
  }, [chamado]);

  const enderecoFormatado = useMemo(() => {
    if (!chamado) return { linha1: "", linha2: "" };

    const c = chamado;
    const endereco = c.endereco ?? c.endereco_cliente ?? c.endereco_entrega ?? "";
    const numero = c.numero ?? "";
    const bairro = c.bairro ?? "";
    const cidade = c.cidade ?? "";
    const uf = c.uf ?? "";

    const linha1 = endereco ? `${endereco}${numero ? ", " + numero : ""}${bairro ? " - " + bairro : ""}` : "";
    const linha2 = cidade ? `${cidade}${uf ? " - " + uf : ""}` : "";

    return { linha1, linha2 };
  }, [chamado]);

  const mapRegion = useMemo(() => {
    if (!chamado) return DEFAULT_REGION;
    const lat = chamado.latitude ?? chamado.lat ?? null;
    const lng = chamado.longitude ?? chamado.lng ?? chamado.lon ?? null;
    if (lat && lng) {
      return {
        latitude: Number(lat),
        longitude: Number(lng),
        latitudeDelta: 0.01,
        longitudeDelta: 0.01,
      };
    }
    return DEFAULT_REGION;
  }, [chamado]);

  if (loading) {
    return (
      <View style={styles.loader}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  if (!chamado) {
    return (
      <View style={styles.loader}>
        <Text>Chamado não encontrado.</Text>
      </View>
    );
  }

  const visita = chamado?.visitas?.[0];

  async function handleAcaoPrincipal() {
    if (!visita || !estado) return;

    const visitaId = visita.id_visita;

    if (estado.pode_iniciar_deslocamento_ida) {
      router.push({
        pathname: "/detalheChamado/DeslocamentoInicio",
        params: { chamadoId: chamado.id_os, visitaId, tipo: "ida" },
      });
      return;
    }

    if (estado.pode_finalizar_deslocamento_ida) {
      router.push({
        pathname: "/detalheChamado/DeslocamentoFim",
        params: { chamadoId: chamado.id_os, visitaId, tipo: "ida" },
      });
      return;
    }

    if (estado.pode_iniciar_atendimento) {
      try {
        await iniciarAtendimentoVisita(chamado.id_os, visita.id_visita);
        Alert.alert("Sucesso", "Atendimento iniciado!");
        await loadChamado();
      } catch (err) {
        alertError(err, "Erro ao iniciar atendimento.");
      }
      return;
    }

    if (estado.pode_finalizar_atendimento) {
      router.push({
        pathname: "/detalheChamado/Assinatura",
        params: { chamadoId: chamado.id_os, visitaId },
      });
      return;
    }

    if (estado.pode_iniciar_deslocamento_volta) {
      router.push({
        pathname: "/detalheChamado/DeslocamentoInicio",
        params: { chamadoId: chamado.id_os, visitaId, tipo: "volta" },
      });
      return;
    }

    if (estado.pode_finalizar_deslocamento_volta) {
      router.push({
        pathname: "/detalheChamado/DeslocamentoFim",
        params: { chamadoId: chamado.id_os, visitaId, tipo: "volta" },
      });
      return;
    }

    if (estado.pode_concluir_chamado) {
      try {
        await concluirChamado(chamado.id_os);

        Alert.alert("Chamado concluído!", "O chamado foi totalmente finalizado.");
        router.replace("/Home/indexHome");

      } catch (err) {
        Alert.alert("Erro", "Falha ao concluir o chamado.");
        console.error(err);
      }

      return;
    }
  }

  function getTextoBotao() {
    if (!estado) return "Aguarde...";

    if (estado.pode_iniciar_deslocamento_ida) return "Iniciar deslocamento";
    if (estado.pode_finalizar_deslocamento_ida) return "Finalizar deslocamento";
    if (estado.pode_iniciar_atendimento) return "Iniciar atendimento";
    if (estado.pode_finalizar_atendimento) return "Finalizar atendimento";
    if (estado.pode_iniciar_deslocamento_volta) return "Iniciar deslocamento";
    if (estado.pode_finalizar_deslocamento_volta) return "Finalizar deslocamento";
    if (estado.pode_concluir_chamado) return "Concluir chamado";

    return "Ação indisponível";
  }

  return (
    <View style={{ flex: 1 }}>
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.replace("/Home/indexHome")} />

      <ScrollView style={styles.container}>
        
        {/* Top */}
        <View style={styles.top}>
          <Text style={styles.osTitle}>OS #{chamado.pedido ?? chamado.id_os}</Text>

          <View style={{ marginTop: 8, marginBottom: 12 }}>
            <Button
              title={getTextoBotao()}
              onPress={handleAcaoPrincipal}
              width="100%"
              fontSize={15}
            />
          </View>

          <Text style={styles.descricao}>
            {chamado.descricao_cliente ?? chamado.descricao ?? "Sem descrição"}
          </Text>
        </View>

        {/* Equipamentos */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>EQUIPAMENTOS</Text>

          <View style={styles.equipList}>
            {equipamentos.length === 0 ? (
              <View style={styles.emptyEquip}>
                <Text style={styles.emptyEquipText}>Nenhum equipamento.</Text>
              </View>
            ) : (
              equipamentos.map((equip: any, idx: number) => (
                <View key={idx} style={styles.equipCardWrapper}>
                  <CardEquipamento
                    equip={equip}
                    disabled={!estado?.pode_finalizar_atendimento}
                    onPress={() => {
                      // navega para registro de defeito
                      router.push({
                        pathname: "/detalheChamado/registroEquipamento",
                        params: {
                          chamadoId: chamado.id_os,
                          visitaId: visita.id_visita,
                          servicoId: equip.id_servico,
                          numeroSerie: equip.numero_serie_atendido
                        }
                      })
                    }}
                  />
                </View>
              ))
            )}
          </View>
        </View>

        {/* Cliente */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>CLIENTE</Text>

          <Text style={styles.clienteTitle}>
            {chamado.cliente_nome ?? "Cliente não informado"}
          </Text>

          <View style={styles.clientCard}>
            <Text style={styles.clientLabel}>Endereço</Text>
            <Text style={styles.clientAddress}>{enderecoFormatado.linha1}</Text>
            <Text style={styles.clientAddress}>{enderecoFormatado.linha2}</Text>

            <View style={styles.mapContainer}>
              <MapView
                provider={PROVIDER_GOOGLE}
                style={styles.map}
                initialRegion={mapRegion}
                region={mapRegion}
              >
                {chamado.latitude && chamado.longitude && (
                  <Marker
                    coordinate={{
                      latitude: Number(chamado.latitude),
                      longitude: Number(chamado.longitude),
                    }}
                    title={chamado.cliente_nome ?? "Local"}
                    description={enderecoFormatado.linha1}
                  />
                )}
              </MapView>
            </View>
          </View>
        </View>

      </ScrollView>
    </View>
  );
}
function updateVisita(id_os: any, visitaId: any, arg2: { hora_inicio_atendimento: string; }) {
  throw new Error("Function not implemented.");
}

