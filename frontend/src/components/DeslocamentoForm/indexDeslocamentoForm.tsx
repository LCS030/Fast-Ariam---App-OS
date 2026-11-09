import React, { useState } from "react";
import {
  View,
  Text,
  Image,
  Alert,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Header } from "@/components/header/indexHeader";
import { Button } from "@/components/button/indexButton";
import { Input } from "@/components/input/indexInput";
import { colors } from "@/styles/Colors";
import { alertError } from "@/utils/alerts";
import { capturarFoto, FotoCapturada } from "@/utils/camera";
import { voltarParaOS } from "@/utils/nav";
import { paramNum, paramStr } from "@/utils/params";
import { parseKm } from "@/utils/validators";
import { obterOsLocal } from "@/offline/cacheOS";
import { registrarFimDeslocamento, registrarInicioDeslocamento } from "@/offline/acoes";

/**
 * Iniciar/finalizar deslocamento (ida ou volta): KM + foto do odometro na mesma tela.
 *
 * Offline-first (AR-04): a foto e copiada para o armazenamento privado do app e o evento entra
 * na fila numa unica gravacao local, com o horario do aparelho. O envio acontece depois (arquivo
 * primeiro, evento em seguida); por isso nao existe mais "reenviar so a foto" nem etapas parciais.
 */
export function DeslocamentoForm({ modo }: { modo: "inicio" | "fim" }) {
  const router = useRouter();
  const params = useLocalSearchParams<{
    chamadoId?: string;
    visitaId?: string;
    tipo?: string;
    kmReferencia?: string;
  }>();

  const chamadoId = paramNum(params.chamadoId);
  const visitaId = paramNum(params.visitaId);
  const tipo: "ida" | "volta" = paramStr(params.tipo) === "volta" ? "volta" : "ida";
  const kmReferencia = paramNum(params.kmReferencia); // KM inicial desta etapa (so no modo fim)

  const [km, setKm] = useState("");
  const [kmErro, setKmErro] = useState<string | null>(null);
  const [foto, setFoto] = useState<FotoCapturada | null>(null);
  const [capturando, setCapturando] = useState(false);
  const [loading, setLoading] = useState(false);

  const titulo =
    modo === "inicio" ? `Iniciar deslocamento (${tipo})` : `Finalizar deslocamento (${tipo})`;
  const rotuloKm = modo === "inicio" ? "KM inicial do odômetro" : "KM final do odômetro";
  const rotuloFoto = modo === "inicio" ? "Foto do odômetro (início)" : "Foto do odômetro (fim)";

  if (chamadoId === null || visitaId === null) {
    return (
      <View style={{ flex: 1 }}>
        <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />
        <View style={styles.centro}>
          <Text style={styles.erro}>OS ou visita não identificadas. Volte e tente novamente.</Text>
        </View>
      </View>
    );
  }

  async function tirarFoto() {
    if (capturando || loading) return;
    try {
      setCapturando(true);
      const nova = await capturarFoto("outra"); // odometro: sem resolucao minima
      if (nova) setFoto(nova);
    } catch {
      Alert.alert("Erro", "Falha ao capturar a foto. Tente novamente.");
    } finally {
      setCapturando(false);
    }
  }

  function validar(): number | null {
    const valor = parseKm(km);
    if (valor === null) {
      setKmErro("Informe o KM do odômetro com números inteiros (sem vírgula).");
      return null;
    }
    if (modo === "fim" && kmReferencia !== null && valor < kmReferencia) {
      setKmErro(`O KM final não pode ser menor que o KM inicial (${kmReferencia}).`);
      return null;
    }
    setKmErro(null);
    if (!foto) {
      Alert.alert("Foto obrigatória", "Tire a foto do odômetro antes de continuar.");
      return null;
    }
    return valor;
  }

  /** Mensagem final a partir do estado LOCAL (ja considera a acao recem-gravada). */
  async function mensagemFinal(): Promise<string> {
    const base = "Salvo no aparelho; será enviado quando houver conexão.";
    if (tipo === "ida") return `Deslocamento de ida finalizado. ${base}`;
    try {
      const os = await obterOsLocal(chamadoId as number);
      if (os?.chamado.status === "Finalizado") return `Deslocamento finalizado. A OS foi finalizada. ${base}`;
      if (os?.chamado.status === "Aguardando Reagendamento") {
        return `Visita encerrada. A OS aguarda o reagendamento pelo administrador. ${base}`;
      }
    } catch {
      // a mensagem generica abaixo basta; o detalhe da OS recarrega o status
    }
    return `Deslocamento finalizado. ${base}`;
  }

  async function confirmar() {
    if (loading) return;
    const kmNumero = validar();
    if (kmNumero === null || !foto) return;

    const ctx = { idOs: chamadoId as number, idVisita: visitaId as number };

    setLoading(true);
    try {
      if (modo === "inicio") {
        await registrarInicioDeslocamento(ctx, tipo, kmNumero, foto);
        Alert.alert("Deslocamento iniciado", "Salvo no aparelho; será enviado quando houver conexão.");
      } else {
        await registrarFimDeslocamento(ctx, tipo, kmNumero, foto);
        Alert.alert("Sucesso", await mensagemFinal());
      }
      voltarParaOS(router, ctx.idOs);
    } catch (err) {
      // Dados digitados e foto permanecem na tela para nova tentativa.
      alertError(
        err,
        modo === "inicio" ? "Falha ao iniciar o deslocamento." : "Falha ao finalizar o deslocamento."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: "#fff" }}
    >
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.titulo}>{titulo}</Text>

        {modo === "fim" && kmReferencia !== null && (
          <Text style={styles.dica}>KM inicial desta etapa: {kmReferencia}</Text>
        )}

        <Input
          label={rotuloKm}
          value={km}
          onChangeText={(t) => {
            setKm(t.replace(/\D/g, ""));
            setKmErro(null);
          }}
          keyboardType="numeric"
          placeholder="0"
          maxLength={9}
          editable={!loading}
          error={kmErro}
        />

        <Text style={styles.rotulo}>{rotuloFoto}</Text>
        <View style={styles.previa}>
          {foto ? (
            <Image source={{ uri: foto.uri }} style={styles.imagem} resizeMode="contain" />
          ) : (
            <Text style={styles.placeholder}>Sem foto</Text>
          )}
        </View>

        <View style={{ marginTop: 16, gap: 12 }}>
          <Button
            title={foto ? "Tirar nova foto" : "Tirar foto do odômetro"}
            variant="secondary"
            onPress={tirarFoto}
            width="100%"
            disabled={capturando || loading}
          />
          <Button
            title={modo === "inicio" ? "Iniciar deslocamento" : "Finalizar deslocamento"}
            onPress={confirmar}
            width="100%"
            loading={loading}
          />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  centro: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  erro: { color: colors.red[900], fontSize: 15, textAlign: "center" },
  titulo: { fontSize: 20, fontWeight: "700", color: colors.blue[900], marginBottom: 16 },
  dica: { color: colors.gray[500], marginBottom: 12, fontSize: 14 },
  rotulo: { color: colors.gray[800], fontSize: 14, marginBottom: 6 },
  previa: {
    height: 280,
    borderWidth: 1,
    borderColor: colors.gray[200],
    borderRadius: 12,
    backgroundColor: colors.gray[100],
    overflow: "hidden",
    justifyContent: "center",
    alignItems: "center",
  },
  imagem: { width: "100%", height: "100%" },
  placeholder: { color: colors.gray[400], fontSize: 16 },
});
