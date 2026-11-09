import React, { useRef, useState } from "react";
import { View, Text, Image, Alert, ActivityIndicator, ScrollView, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Header } from "@/components/header/indexHeader";
import { Button } from "@/components/button/indexButton";
import { colors } from "@/styles/Colors";
import { alertError } from "@/utils/alerts";
import { voltarParaOS } from "@/utils/nav";
import { capturarFoto, FotoCapturada, CONSERTO_MIN_LADO_MENOR, CONSERTO_MIN_LADO_MAIOR } from "@/utils/camera";
import { registrarFotoServico } from "@/offline/acoes";

interface Props {
  tipo: "defeito" | "conserto";
  chamadoId: number | null;
  visitaId: number | null;
  servicoId: number | null;
  /** Modelo + serie do equipamento (somente leitura), apenas para identificar a foto. */
  equipamento?: string;
}

const TEXTOS = {
  defeito: {
    titulo: "Foto do Defeito",
    subtitulo: "Tire uma foto do equipamento com o defeito. Ela é obrigatória antes de iniciar o atendimento.",
  },
  conserto: {
    titulo: "Foto do Conserto",
    subtitulo:
      `Tire uma foto do equipamento após o reparo para comprovar a execução. ` +
      `Mínimo ${CONSERTO_MIN_LADO_MENOR}x${CONSERTO_MIN_LADO_MAIOR} px, em retrato ou paisagem.`,
  },
} as const;

/**
 * Captura + envio de foto de servico.
 * Conserto: valida 960x1280 na captura (RN-21/RN-37). Defeito: sem resolucao minima (CA-14).
 * Ambas: JPEG/PNG ate 15 MB (CA-15).
 */
export function FotoCapturaScreen({ tipo, chamadoId, visitaId, servicoId, equipamento }: Props) {
  const router = useRouter();
  const [foto, setFoto] = useState<FotoCapturada | null>(null);
  const [capturando, setCapturando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const enviandoRef = useRef(false); // trava sincrona contra duplo toque

  const textos = TEXTOS[tipo];
  const paramsInvalidos = !chamadoId || !visitaId || !servicoId;

  async function tirarFoto() {
    if (capturando || enviando) return;
    try {
      setCapturando(true);
      const nova = await capturarFoto(tipo === "conserto" ? "conserto" : "outra");
      if (nova) setFoto(nova);
    } catch {
      Alert.alert("Erro", "Falha ao capturar a foto. Tente novamente.");
    } finally {
      setCapturando(false);
    }
  }

  async function enviar() {
    if (!foto || enviandoRef.current || paramsInvalidos) return;
    enviandoRef.current = true;
    setEnviando(true);
    try {
      // Offline-first: copia a foto para o armazenamento privado e grava a acao na fila;
      // o envio (arquivo primeiro, depois o evento) acontece em segundo plano.
      await registrarFotoServico({ idOs: chamadoId!, idVisita: visitaId! }, servicoId!, tipo, foto);
      Alert.alert("Foto salva", `Foto do ${tipo} salva no aparelho; será enviada quando houver conexão.`);
      voltarParaOS(router, chamadoId!);
    } catch (err) {
      // A foto permanece na tela para o tecnico tentar novamente.
      alertError(err, `Falha ao salvar a foto do ${tipo}.`);
    } finally {
      enviandoRef.current = false;
      setEnviando(false);
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: "#fff" }}>
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />

      <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 24 }}>
        <View style={{ marginTop: 20, marginBottom: 20 }}>
          <Text style={styles.title}>{textos.titulo}</Text>
          {equipamento ? <Text style={styles.equipamento}>{equipamento}</Text> : null}
          <Text style={styles.subtitle}>{textos.subtitulo}</Text>
        </View>

        {paramsInvalidos ? (
          <Text style={styles.erro}>
            Equipamento ou visita não identificados. Volte e selecione o equipamento novamente.
          </Text>
        ) : (
          <>
            <View style={styles.imageContainer}>
              {foto ? (
                <Image source={{ uri: foto.uri }} style={styles.image} resizeMode="contain" />
              ) : capturando ? (
                <View style={styles.centro}>
                  <ActivityIndicator size="large" color={colors.blue[900]} />
                  <Text style={styles.loadingText}>Capturando foto...</Text>
                </View>
              ) : (
                <Text style={styles.placeholderText}>Nenhuma foto capturada</Text>
              )}
            </View>

            <View style={{ marginTop: 20, gap: 12 }}>
              <Button
                title={foto ? "Tirar Nova Foto" : "Tirar Foto"}
                onPress={tirarFoto}
                width="100%"
                disabled={capturando || enviando}
              />

              {foto && (
                <>
                  <Button
                    title="Descartar Foto"
                    variant="secondary"
                    onPress={() => setFoto(null)}
                    width="100%"
                    disabled={enviando}
                  />
                  <Button
                    title="Confirmar e Salvar"
                    onPress={enviar}
                    width="100%"
                    loading={enviando}
                  />
                </>
              )}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: 16 },
  title: { fontSize: 24, fontWeight: "700", color: colors.blue[900], marginBottom: 8 },
  equipamento: { fontSize: 15, fontWeight: "700", color: colors.gray[800], marginBottom: 8 },
  subtitle: { fontSize: 14, color: colors.gray[500], lineHeight: 20 },
  erro: { fontSize: 15, color: colors.red[900] },
  imageContainer: {
    width: "100%",
    height: 320,
    backgroundColor: colors.gray[100],
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 2,
    borderColor: colors.gray[200],
    justifyContent: "center",
    alignItems: "center",
  },
  image: { width: "100%", height: "100%" },
  centro: { justifyContent: "center", alignItems: "center" },
  loadingText: { marginTop: 12, fontSize: 14, color: colors.gray[500] },
  placeholderText: { fontSize: 16, color: colors.gray[400] },
});
