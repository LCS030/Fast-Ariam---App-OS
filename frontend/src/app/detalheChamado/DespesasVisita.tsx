import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  Image,
  Alert,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Header } from "@/components/header/indexHeader";
import { Button } from "@/components/button/indexButton";
import { Input } from "@/components/input/indexInput";
import { colors } from "@/styles/Colors";
import { alertError, getErrorMessage } from "@/utils/alerts";
import { obterOsLocal } from "@/offline/cacheOS";
import { registrarDespesas } from "@/offline/acoes";
import { capturarFoto, FotoCapturada } from "@/utils/camera";
import { voltarParaOS } from "@/utils/nav";
import { paramNum } from "@/utils/params";
import { parseValor } from "@/utils/validators";

type Tipo = "pedagio" | "frete";

/**
 * Pedagio e frete de devolucao da visita (RN-20): se o valor for maior que zero, o
 * comprovante e obrigatorio. Offline-first: cada comprovante vira um evento
 * `comprovante_registrado` (valor + foto) na fila do aparelho; o servidor revalida na finalizacao.
 */
export default function DespesasVisitaScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ chamadoId?: string; visitaId?: string }>();
  const chamadoId = paramNum(params.chamadoId);
  const visitaId = paramNum(params.visitaId);

  const [carregando, setCarregando] = useState(true);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [valores, setValores] = useState<Record<Tipo, string>>({ pedagio: "", frete: "" });
  const [erros, setErros] = useState<Partial<Record<Tipo, string>>>({});
  const [fotos, setFotos] = useState<Record<Tipo, FotoCapturada | null>>({
    pedagio: null,
    frete: null,
  });
  const [jaEnviados, setJaEnviados] = useState<Record<Tipo, number>>({ pedagio: 0, frete: 0 });
  // Valores ja registrados (servidor + fila): so ha o que salvar se mudarem ou houver foto nova.
  const [registrados, setRegistrados] = useState<Record<Tipo, number>>({ pedagio: 0, frete: 0 });
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    if (chamadoId === null || visitaId === null) {
      setErroCarga("OS ou visita não identificadas.");
      setCarregando(false);
      return;
    }
    try {
      setCarregando(true);
      const os = await obterOsLocal(chamadoId);
      if (!os || !os.visita || os.visita.id_visita !== visitaId) {
        setErroCarga("Visita não encontrada no aparelho. Conecte-se e sincronize.");
        return;
      }
      const d = os.despesas;
      const texto = (n?: number | null) => (n ? String(n).replace(".", ",") : "");
      setValores({ pedagio: texto(d.valor_pedagio), frete: texto(d.valor_frete) });
      setRegistrados({ pedagio: d.valor_pedagio, frete: d.valor_frete });
      setJaEnviados({ pedagio: d.comprovantes_pedagio, frete: d.comprovantes_frete });
      setErroCarga(null);
    } catch (err) {
      setErroCarga(getErrorMessage(err, "Falha ao carregar a visita."));
    } finally {
      setCarregando(false);
    }
  }, [chamadoId, visitaId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function tirarFoto(tipo: Tipo) {
    if (salvando) return;
    try {
      const foto = await capturarFoto("outra"); // comprovante: sem resolucao minima
      if (foto) {
        setFotos((f) => ({ ...f, [tipo]: foto }));
        setErros((e) => ({ ...e, [tipo]: undefined }));
      }
    } catch {
      Alert.alert("Erro", "Falha ao capturar a foto. Tente novamente.");
    }
  }

  async function salvar() {
    if (salvando || chamadoId === null || visitaId === null) return;

    const pedagio = parseValor(valores.pedagio);
    const frete = parseValor(valores.frete);
    const novos: Partial<Record<Tipo, string>> = {};
    const aSalvar: { tipo: Tipo; valor: number; foto: FotoCapturada }[] = [];

    const avaliar = (tipo: Tipo, valor: number | null, rotulo: string) => {
      if (valor === null) {
        novos[tipo] = "Valor inválido. Use números, ex.: 12,50.";
        return;
      }
      const mudou = valor !== registrados[tipo];
      const foto = fotos[tipo];
      if (!mudou && !foto) return; // nada novo neste item
      if (valor <= 0) {
        novos[tipo] = `Informe o valor do ${rotulo} (maior que zero) para registrar o comprovante.`;
      } else if (!foto) {
        // Cada registro leva o comprovante (foto) junto com o valor.
        novos[tipo] = `Anexe o comprovante do ${rotulo}.`;
      } else {
        aSalvar.push({ tipo, valor, foto });
      }
    };
    avaliar("pedagio", pedagio, "pedágio");
    avaliar("frete", frete, "frete de devolução");

    setErros(novos);
    if (Object.keys(novos).length > 0) return;
    if (aSalvar.length === 0) {
      Alert.alert("Nada a salvar", "Nenhum valor ou comprovante novo foi informado.");
      return;
    }

    setSalvando(true);
    try {
      // Fotos vao para o armazenamento privado e os eventos para a fila, numa unica gravacao local.
      await registrarDespesas({ idOs: chamadoId, idVisita: visitaId }, aSalvar);
      setFotos({ pedagio: null, frete: null });
      Alert.alert(
        "Pedágio e frete salvos",
        "Salvo no aparelho; será enviado quando houver conexão."
      );
      voltarParaOS(router, chamadoId);
    } catch (err) {
      // Valores e fotos pendentes continuam na tela para nova tentativa.
      alertError(err, "Falha ao salvar pedágio e frete.");
    } finally {
      setSalvando(false);
    }
  }

  function bloco(tipo: Tipo, titulo: string, rotuloValor: string) {
    const foto = fotos[tipo];
    return (
      <View style={styles.bloco}>
        <Text style={styles.subtitulo}>{titulo}</Text>
        <Input
          label={rotuloValor}
          value={valores[tipo]}
          onChangeText={(t) => {
            setValores((v) => ({ ...v, [tipo]: t.replace(/[^0-9.,]/g, "") }));
            setErros((e) => ({ ...e, [tipo]: undefined }));
          }}
          keyboardType="decimal-pad"
          placeholder="0,00"
          maxLength={10}
          editable={!salvando}
          error={erros[tipo]}
        />

        {jaEnviados[tipo] > 0 && (
          <Text style={styles.ok}>
            {jaEnviados[tipo]} comprovante(s) registrado(s).
          </Text>
        )}

        {foto && <Image source={{ uri: foto.uri }} style={styles.imagem} resizeMode="contain" />}

        <Button
          title={foto ? "Tirar nova foto do comprovante" : "Tirar foto do comprovante"}
          variant="secondary"
          onPress={() => tirarFoto(tipo)}
          disabled={salvando}
          width="100%"
          fontSize={14}
        />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: "#fff" }}
    >
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />

      {carregando ? (
        <View style={styles.centro}>
          <ActivityIndicator size="large" />
        </View>
      ) : erroCarga ? (
        <View style={styles.centro}>
          <Text style={styles.erro}>{erroCarga}</Text>
          <Button title="Tentar novamente" onPress={carregar} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.titulo}>Pedágio e frete</Text>
          <Text style={styles.dica}>
            Informe os valores da visita. Para valor maior que zero, o comprovante é obrigatório.
            Deixe em branco se não houve.
          </Text>

          {bloco("pedagio", "Pedágio", "Valor total de pedágios (R$)")}
          {bloco("frete", "Frete de devolução", "Valor do frete de devolução (R$)")}

          <Button title="Salvar" onPress={salvar} loading={salvando} width="100%" />
        </ScrollView>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  centro: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24, gap: 16 },
  erro: { color: colors.red[900], textAlign: "center", fontSize: 15 },
  titulo: { fontSize: 20, fontWeight: "700", color: colors.blue[900], marginBottom: 8 },
  dica: { color: colors.gray[500], fontSize: 14, marginBottom: 16 },
  bloco: {
    borderWidth: 1,
    borderColor: colors.gray[200],
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
    gap: 8,
  },
  subtitulo: { fontSize: 16, fontWeight: "700", color: colors.blue[900] },
  ok: { color: colors.green[500], fontWeight: "700", fontSize: 13 },
  imagem: { width: "100%", height: 200, borderRadius: 8, backgroundColor: colors.gray[100] },
});
