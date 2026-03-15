import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  SafeAreaView,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";

import { Header } from "@/components/header/indexHeader";
import { CardChamado } from "@/components/CardChamado/indexCardChamado";
import { listarChamados } from "@/api/chamado";
import { getToken, removeToken } from "@/utils/storage";
import { alertError } from "@/utils/alerts";
import { styles } from "../../styles/styleHome";




export default function HomeScreen() {
  const router = useRouter();
  const [chamados, setChamados] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  
  useEffect(() => {
      getToken().then((t) => console.log("TOKEN ATUAL:", t));
    }, []);

  const loadChamados = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listarChamados();
      setChamados(Array.isArray(data) ? data : []);
    } catch (err) {
      alertError(err, "Falha ao carregar chamados.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadChamados();
  }, [loadChamados]);

  const onRefresh = useCallback(async () => {


    try {
      setRefreshing(true);
      const data = await listarChamados();
      setChamados(Array.isArray(data) ? data : []);
    } catch (err) {
      alertError(err, "Falha ao atualizar chamados.");
    } finally {
      setRefreshing(false);
    }
    
  }, []);

  async function handleLogout() {
    // Confirmação simples
    Alert.alert("Logout", "Deseja sair da conta?", [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Sair",
        style: "destructive",
        onPress: async () => {
          await removeToken();
          router.replace("/login/indexLogin");
        },
      },
    ]);
  }

  return (
    <SafeAreaView style={{ flex: 1 }}>
      {/* Header sem título; left icon = logout */}
      <Header leftIconName="logout" onLeftIconPress={handleLogout} />

      <View style={styles.container}>
        <Text style={styles.title}>Meus Chamados</Text>

        {loading ? (
          <View style={styles.loader}>
            <ActivityIndicator size="large" />
          </View>
        ) : (
          <FlatList
                data={chamados}
                keyExtractor={(item) => String(item.id_os)}
                renderItem={({ item }) => <CardChamado chamado={item} />}
                contentContainerStyle={chamados.length === 0 ? styles.emptyContainer : undefined}
                refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
                ListEmptyComponent={
                    <View style={styles.emptyBox}>
                    <Text style={styles.emptyText}>Nenhum chamado disponível.</Text>
                    </View>
                }
            />
        )}
      </View>
    </SafeAreaView>
  );
}

