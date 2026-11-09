import React, { useState, useCallback } from "react";
import {
  View,
  Text,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter, useFocusEffect } from "expo-router";

import { Header } from "@/components/header/indexHeader";
import { CardChamado } from "@/components/CardChamado/indexCardChamado";
import { Button } from "@/components/button/indexButton";
import { removeToken } from "@/utils/storage";
import { getErrorMessage } from "@/utils/alerts";
import { styles } from "../../styles/styleHome";
import { styleAviso } from "@/styles/styleAviso";
import { colors } from "@/styles/Colors";
import { listarOsLocal, OsLocal, ultimaAtualizacaoCache } from "@/offline/cacheOS";
import { encerrarSessao, getSessao, MSG_SESSAO } from "@/offline/sessao";
import { atualizarContagens } from "@/offline/status";
import { sincronizar } from "@/offline/sync";
import { getStatus, useStatusOffline, useVersaoLocal } from "@/offline/store";

export default function HomeScreen() {
  const router = useRouter();
  const status = useStatusOffline();
  const versao = useVersaoLocal(); // muda quando o cache ou a fila mudam: recarrega a lista
  const [lista, setLista] = useState<OsLocal[] | null>(null); // null = ainda nao leu
  const [nome, setNome] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [nuncaSincronizou, setNuncaSincronizou] = useState(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [avisoSync, setAvisoSync] = useState<string | null>(null);

  // A lista vem do aparelho (RF-22): funciona sem internet. Falha de leitura NUNCA vira lista
  // vazia nem dado ficticio.
  const carregar = useCallback(async () => {
    try {
      const [os, sessao, ultimo] = await Promise.all([
        listarOsLocal(),
        getSessao(),
        ultimaAtualizacaoCache(),
      ]);
      setLista(os);
      setNome(sessao?.nome ?? null);
      setNuncaSincronizou(ultimo === null);
      setErro(null);
    } catch (err) {
      setErro(getErrorMessage(err, "Falha ao ler as OS salvas no aparelho."));
    } finally {
      setLoading(false);
    }
    // `versao` so serve para refazer esta funcao (e a leitura) quando os dados locais mudam.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versao]);

  useFocusEffect(
    useCallback(() => {
      carregar();
    }, [carregar])
  );

  async function sincronizarAgora() {
    setRefreshing(true);
    setAvisoSync(null);
    try {
      const r = await sincronizar();
      if (!r.ok) {
        setAvisoSync(
          r.motivo === "offline"
            ? "Sem conexão. Mostrando as OS salvas no aparelho."
            : r.mensagem ?? "Não foi possível sincronizar agora."
        );
      }
    } finally {
      setRefreshing(false);
      await carregar();
    }
  }

  function handleLogout() {
    const pendentes = getStatus().pendentes;
    const aviso =
      pendentes > 0
        ? `Há ${pendentes} ${pendentes === 1 ? "ação" : "ações"} ainda não enviada(s). Elas continuam guardadas no aparelho, mas só serão enviadas quando você entrar de novo com esta conta e houver internet.\n\nDeseja sair?`
        : "Deseja sair da conta?";
    Alert.alert("Logout", aviso, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Sair",
        style: "destructive",
        onPress: async () => {
          // So a sessao e o token saem; a fila de envio e o cache permanecem (RN-39).
          await removeToken();
          await encerrarSessao();
          await atualizarContagens();
          router.replace("/login/indexLogin");
        },
      },
    ]);
  }

  const semDados = lista === null;
  const bloqueada = status.situacaoSessao === "offline_expirada";

  return (
    <SafeAreaView style={{ flex: 1 }} edges={["bottom"]}>
      <Header leftIconName="logout" onLeftIconPress={handleLogout} />

      <View style={styles.container}>
        <Text style={styles.title}>Meus Chamados</Text>
        {nome ? <Text style={styles.subtitle}>Olá, {nome}</Text> : null}

        {bloqueada ? (
          <View style={styleAviso.box}>
            <Text style={styleAviso.titulo}>Sessão offline encerrada</Text>
            <Text style={styleAviso.texto}>{MSG_SESSAO.offline_expirada}</Text>
            <View style={{ marginTop: 8 }}>
              <Button
                title="Entrar novamente"
                onPress={() => router.replace("/login/indexLogin")}
                width="100%"
                fontSize={14}
              />
            </View>
          </View>
        ) : status.situacaoSessao === "jwt_expirado" ? (
          <View style={styleAviso.box}>
            <Text style={styleAviso.titulo}>Sessão expirada</Text>
            <Text style={styleAviso.texto}>{MSG_SESSAO.jwt_expirado}</Text>
            <View style={{ marginTop: 8 }}>
              <Button
                title="Entrar novamente"
                onPress={() => router.replace("/login/indexLogin")}
                width="100%"
                fontSize={14}
              />
            </View>
          </View>
        ) : null}

        {loading && semDados ? (
          <View style={styles.loader}>
            <ActivityIndicator size="large" />
          </View>
        ) : semDados ? (
          <View style={styles.emptyContainer}>
            <View style={styles.emptyBox}>
              <Text style={[styles.emptyText, { color: colors.red[900], marginBottom: 12 }]}>
                {erro ?? "Falha ao carregar chamados."}
              </Text>
              <Button title="Tentar novamente" onPress={carregar} />
            </View>
          </View>
        ) : (
          <>
            {erro ? (
              <Text style={styles.erroBanner}>Não foi possível atualizar a lista: {erro}</Text>
            ) : null}
            {avisoSync ? <Text style={styles.erroBanner}>{avisoSync}</Text> : null}
            <FlatList
              data={lista}
              keyExtractor={(item) => String(item.chamado.id_os)}
              renderItem={({ item }) => (
                <CardChamado chamado={item.chamado} pendentes={item.acoesPendentes} />
              )}
              contentContainerStyle={lista.length === 0 ? styles.emptyContainer : undefined}
              refreshControl={
                <RefreshControl refreshing={refreshing} onRefresh={sincronizarAgora} />
              }
              ListEmptyComponent={
                <View style={styles.emptyBox}>
                  <Text style={styles.emptyText}>
                    {nuncaSincronizou
                      ? "Ainda não há OS salvas neste aparelho. Conecte-se à internet e puxe a lista para sincronizar."
                      : "Nenhum chamado atribuído a você."}
                  </Text>
                  {nuncaSincronizou ? (
                    <View style={{ marginTop: 12 }}>
                      <Button title="Sincronizar agora" onPress={sincronizarAgora} />
                    </View>
                  ) : null}
                </View>
              }
            />
          </>
        )}
      </View>
    </SafeAreaView>
  );
}
