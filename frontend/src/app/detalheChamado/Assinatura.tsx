import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  Alert,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { AssinaturaCanvas } from "@/components/AssinaturaCanvas/indexAssinaturaCanvas";
import { Header } from "@/components/header/indexHeader";
import { Input } from "@/components/input/indexInput";
import { Button } from "@/components/button/indexButton";
import { colors } from "@/styles/Colors";
import type { EstadoVisita } from "@/api/visitas";
import { alertError, getErrorMessage } from "@/utils/alerts";
import { voltarParaOS } from "@/utils/nav";
import { paramNum } from "@/utils/params";
import { cpfValido, mascararCpf } from "@/utils/validators";
import { obterOsLocal } from "@/offline/cacheOS";
import { registrarFimAtendimento } from "@/offline/acoes";
import { useVersaoLocal } from "@/offline/store";

export default function AssinaturaFinalizacao() {
  const router = useRouter();
  const params = useLocalSearchParams<{ chamadoId?: string; visitaId?: string }>();
  const chamadoId = paramNum(params.chamadoId);
  const visitaId = paramNum(params.visitaId);

  const [nomeCliente, setNomeCliente] = useState("");
  const [cpf, setCpf] = useState("");
  const [signature, setSignature] = useState<string | null>(null);
  const [erros, setErros] = useState<{ nome?: string; cpf?: string; assinatura?: string }>({});
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false); // trava sincrona contra duplo toque

  // Estado da visita (fonte de verdade): checklist de pendencias por equipamento.
  const [estado, setEstado] = useState<EstadoVisita | null>(null);
  const [carregandoEstado, setCarregandoEstado] = useState(true);
  const [erroEstado, setErroEstado] = useState<string | null>(null);

  const versao = useVersaoLocal();

  // Estado LOCAL (servidor + acoes ainda nao enviadas): funciona sem internet.
  const carregarEstado = useCallback(async () => {
    if (chamadoId === null || visitaId === null) return;
    try {
      const os = await obterOsLocal(chamadoId);
      if (!os?.estado) {
        setEstado(null);
        setErroEstado(
          "O estado desta visita não está salvo no aparelho. Conecte-se e sincronize antes de finalizar."
        );
      } else {
        setEstado(os.estado);
        setErroEstado(null);
      }
    } catch (e) {
      setErroEstado(getErrorMessage(e, "Falha ao carregar as pendências do atendimento."));
    } finally {
      setCarregandoEstado(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chamadoId, visitaId, versao]);

  useEffect(() => {
    carregarEstado();
  }, [carregarEstado]);

  if (chamadoId === null || visitaId === null) {
    return (
      <View style={{ flex: 1 }}>
        <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />
        <View style={{ flex: 1, justifyContent: "center", padding: 24 }}>
          <Text style={{ color: colors.red[900], textAlign: "center" }}>
            OS ou visita não identificadas. Volte e tente novamente.
          </Text>
        </View>
      </View>
    );
  }

  function validar(): boolean {
    const novos: typeof erros = {};
    if (nomeCliente.trim().length < 2) novos.nome = "Informe o nome de quem assina.";
    if (!cpfValido(cpf)) novos.cpf = "CPF inválido. Confira os 11 dígitos.";
    if (!signature) novos.assinatura = "Colher a assinatura e tocar em \"Salvar Assinatura\".";
    setErros(novos);
    return Object.keys(novos).length === 0;
  }

  function pedirConfirmacao(): Promise<boolean> {
    return new Promise((resolve) => {
      Alert.alert(
        "Finalizar atendimento",
        "Depois de finalizado, o atendimento desta visita não poderá ser alterado. Confirmar?",
        [
          { text: "Cancelar", style: "cancel", onPress: () => resolve(false) },
          { text: "Finalizar", onPress: () => resolve(true) },
        ],
        { cancelable: true, onDismiss: () => resolve(false) }
      );
    });
  }

  async function salvar() {
    if (savingRef.current || !validar() || !signature) return;
    if (!(await pedirConfirmacao())) return;

    savingRef.current = true;
    try {
      setSaving(true);
      // Grava a assinatura (PNG), o nome e o CPF (so digitos, SDD 4.7) na fila do aparelho,
      // com o horario de AGORA; o envio e feito depois (arquivo primeiro, evento em seguida).
      await registrarFimAtendimento(
        { idOs: chamadoId as number, idVisita: visitaId as number },
        { assinaturaBase64: signature, nomeCliente: nomeCliente.trim(), cpf }
      );

      Alert.alert(
        "Atendimento finalizado",
        "Salvo no aparelho; será enviado ao servidor quando houver conexão."
      );
      voltarParaOS(router, chamadoId as number);
    } catch (error) {
      // Nome, CPF e assinatura permanecem preenchidos para nova tentativa. Pendencias
      // (ex.: falta foto do conserto) chegam na mensagem; a checklist e recalculada.
      alertError(error, "Falha ao finalizar o atendimento.");
      await carregarEstado();
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: "#fff" }}
    >
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={{ fontWeight: "700", fontSize: 20, color: colors.blue[900], marginBottom: 16 }}>
          Dados do Cliente
        </Text>

        {/* Checklist de pendencias por equipamento (vem de GET .../estado) */}
        <View style={{ marginBottom: 16 }}>
          <Text style={{ fontWeight: "700", fontSize: 16, color: colors.blue[900], marginBottom: 8 }}>
            Pendências por equipamento
          </Text>

          {carregandoEstado ? (
            <ActivityIndicator color={colors.blue[900]} />
          ) : erroEstado ? (
            <View style={{ gap: 8 }}>
              <Text style={{ color: colors.red[900], fontSize: 14 }}>{erroEstado}</Text>
              <Button title="Tentar novamente" variant="secondary" onPress={carregarEstado} />
            </View>
          ) : estado && estado.equipamentos.length === 0 ? (
            <Text style={{ color: colors.gray[800], fontSize: 14 }}>
              Nenhum equipamento vinculado a esta OS. Contate o escritório.
            </Text>
          ) : (
            estado?.equipamentos.map((e) => (
              <View
                key={e.id_servico}
                style={{
                  padding: 12,
                  marginBottom: 8,
                  backgroundColor: "#fff",
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: colors.gray[200],
                }}
              >
                <Text style={{ color: colors.blue[900], fontWeight: "700", fontSize: 15 }}>
                  {e.modelo}
                </Text>
                <Text style={{ color: colors.gray[800], fontSize: 13, marginBottom: 4 }}>
                  Série: {e.numero_serie || "S/N"}
                </Text>
                <Text style={{ color: colors.gray[800], fontSize: 14 }}>
                  {e.foto_defeito ? "OK" : "Falta"} - foto do defeito
                </Text>
                <Text style={{ color: colors.gray[800], fontSize: 14 }}>
                  {e.conserto_salvo ? "OK" : "Falta"} - conserto salvo
                </Text>
                <Text style={{ color: colors.gray[800], fontSize: 14 }}>
                  {e.foto_conserto ? "OK" : "Falta"} - foto do conserto
                </Text>
              </View>
            ))
          )}

          {estado && !estado.pode_finalizar_atendimento && estado.bloqueio_finalizar_atendimento ? (
            <View
              style={{
                marginTop: 4,
                padding: 12,
                backgroundColor: colors.gray[100],
                borderRadius: 8,
                borderLeftWidth: 4,
                borderLeftColor: colors.blue[900],
              }}
            >
              <Text style={{ color: colors.gray[800], fontSize: 14 }}>
                {estado.bloqueio_finalizar_atendimento}
              </Text>
            </View>
          ) : null}
        </View>

        <Input
          label="Nome de quem assina"
          value={nomeCliente}
          onChangeText={(t) => {
            setNomeCliente(t);
            setErros((e) => ({ ...e, nome: undefined }));
          }}
          placeholder="Nome do cliente"
          autoCapitalize="words"
          maxLength={100}
          editable={!saving}
          error={erros.nome}
        />

        <Input
          label="CPF"
          value={cpf}
          onChangeText={(t) => {
            setCpf(mascararCpf(t));
            setErros((e) => ({ ...e, cpf: undefined }));
          }}
          placeholder="000.000.000-00"
          keyboardType="numeric"
          maxLength={14}
          editable={!saving}
          error={erros.cpf}
        />

        <AssinaturaCanvas
          onOK={(img) => {
            setSignature(img);
            setErros((e) => ({ ...e, assinatura: undefined }));
          }}
          onClear={() => setSignature(null)}
        />

        {signature ? (
          <Text style={{ color: colors.green[500], fontWeight: "700", marginBottom: 12 }}>
            Assinatura registrada.
          </Text>
        ) : null}
        {erros.assinatura ? (
          <Text style={{ color: colors.red[900], fontSize: 13, marginBottom: 12 }}>
            {erros.assinatura}
          </Text>
        ) : null}

        <Button
          title="Finalizar Atendimento"
          onPress={salvar}
          loading={saving}
          disabled={!estado?.pode_finalizar_atendimento}
          width="100%"
        />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
