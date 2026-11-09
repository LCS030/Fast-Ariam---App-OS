// src/app/detalheChamado/registroEquipamento.tsx
import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  View,
  Text,
  ScrollView,
  Alert,
  ActivityIndicator,
  TouchableOpacity,
  TextInput,
  Modal,
  FlatList,
  Pressable,
  Image,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { Header } from "@/components/header/indexHeader";
import { Button } from "@/components/button/indexButton";
import { colors } from "@/styles/Colors";
import type { ServicoPatch } from "@/api/servico";
import type { ServicoEquipamento } from "@/api/chamado";
import { alertError, getErrorMessage } from "@/utils/alerts";
import { obterOsLocal } from "@/offline/cacheOS";
import { salvarConserto, salvarRegistroServico } from "@/offline/acoes";
import { voltarParaOS } from "@/utils/nav";
import { paramNum } from "@/utils/params";
import { parseValor } from "@/utils/validators";
import {
  Option,
  OPTIONS_COMPRESSOR,
  OPTIONS_VAZAMENTO,
  OPTIONS_OUTROS,
  OPTIONS_ILUMINACAO,
  OPTIONS_ESTRUTURA,
  CHAVE_NAO_LOCALIZADO,
  valoresDeChaves,
  chavesDeValores,
  comporPontoDescricao,
  separarPontoDescricao,
} from "@/utils/defeitos";

import Pontos_solda from "../../../assets/images/pontos_solda.png";
import Pontos_estrutura from "../../../assets/images/pontos_estrutura.png";

type CategoriaKey = "compressor" | "vazamento" | "outros" | "iluminacao" | "estrutura";

const OPTIONS_POR_CATEGORIA: Record<CategoriaKey, Option[]> = {
  compressor: OPTIONS_COMPRESSOR,
  vazamento: OPTIONS_VAZAMENTO,
  outros: OPTIONS_OUTROS,
  iluminacao: OPTIONS_ILUMINACAO,
  estrutura: OPTIONS_ESTRUTURA,
};

const TITULO_CATEGORIA: Record<CategoriaKey, string> = {
  compressor: "Compressor",
  vazamento: "Vazamento",
  outros: "Outros (refrigeração)",
  iluminacao: "Iluminação",
  estrutura: "Estrutura",
};

type MaterialForm = { nome: string; quantidade: string; valor: string };

// =====================================================
// MODAL DE MULTI SELECT
// =====================================================
function MultiSelectModal({
  visible,
  options,
  selected,
  onToggle,
  onClose,
  title,
}: {
  visible: boolean;
  options: Option[];
  selected: string[];
  onToggle: (key: string) => void;
  onClose: () => void;
  title?: string;
}) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "center" }}>
        <View
          style={{
            margin: 20,
            backgroundColor: "#fff",
            borderRadius: 8,
            maxHeight: "80%",
            padding: 12,
          }}
        >
          <Text style={{ fontWeight: "700", fontSize: 16, marginBottom: 8 }}>{title}</Text>

          <FlatList
            data={options}
            keyExtractor={(i) => i.key}
            renderItem={({ item }) => {
              const isSelected = selected.includes(item.key);

              return (
                <Pressable
                  onPress={() => onToggle(item.key)}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: isSelected }}
                  style={{
                    minHeight: 48,
                    flexDirection: "row",
                    alignItems: "center",
                  }}
                >
                  <View
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: 4,
                      borderWidth: 1,
                      borderColor: colors.gray[500],
                      justifyContent: "center",
                      alignItems: "center",
                      marginRight: 10,
                    }}
                  >
                    {isSelected && (
                      <View style={{ width: 14, height: 14, backgroundColor: colors.blue[900] }} />
                    )}
                  </View>

                  <Text style={{ flex: 1 }}>{item.label}</Text>
                </Pressable>
              );
            }}
          />

          <View style={{ marginTop: 8, alignItems: "flex-end" }}>
            <Button title="Fechar" onPress={onClose} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

// =====================================================
// TELA PRINCIPAL
// =====================================================
export default function RegistroEquipamentoScreen() {
  const params = useLocalSearchParams<{
    chamadoId?: string;
    visitaId?: string;
    servicoId?: string;
  }>();
  const router = useRouter();

  const chamadoId = paramNum(params.chamadoId);
  const visitaId = paramNum(params.visitaId);
  const servicoIdParam = paramNum(params.servicoId);

  const [loading, setLoading] = useState(servicoIdParam !== null);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [saving, setSaving] = useState<null | "salvar" | "conserto">(null);
  const savingRef = useRef(false); // trava sincrona contra duplo toque

  // Registro de servico do equipamento da OS (criado pelo servidor). Modelo e serie: somente leitura.
  const [servico, setServico] = useState<ServicoEquipamento | null>(null);
  const [erros, setErros] = useState<{ defeitos?: string; materiais?: string }>({});

  const [selecionados, setSelecionados] = useState<Record<CategoriaKey, string[]>>({
    compressor: [],
    vazamento: [],
    outros: [],
    iluminacao: [],
    estrutura: [],
  });

  const [defeitoOutrosDesc, setDefeitoOutrosDesc] = useState("");
  const [vazamentoObservacao, setVazamentoObservacao] = useState("");
  const [materiais, setMateriais] = useState<MaterialForm[]>([]);
  const [categoriaAberta, setCategoriaAberta] = useState<CategoriaKey | null>(null);

  // =====================================================
  // CARREGAR O SERVIÇO DO EQUIPAMENTO
  // =====================================================
  const loadExisting = useCallback(async () => {
    if (chamadoId === null || visitaId === null || servicoIdParam === null) return;
    try {
      setLoading(true);
      setErroCarga(null);

      // Servicos do aparelho: cache do servidor + registros ainda nao enviados (ultimo salvo vence).
      const os = await obterOsLocal(chamadoId);
      if (!os || !os.visita || os.visita.id_visita !== visitaId) {
        setErroCarga("Visita não encontrada no aparelho. Conecte-se e sincronize.");
        return;
      }
      const s = os.servicos.find((x) => x.id_servico === servicoIdParam);

      if (!s) {
        setErroCarga("Equipamento não encontrado nesta visita. Volte e abra a OS novamente.");
        return;
      }

      const ponto = separarPontoDescricao(s.vazamento_ponto_descricao);
      const vazamentoChaves = chavesDeValores(
        OPTIONS_VAZAMENTO,
        s.sub_defeitos_vazamento
      ).filter((k) => !/^\d+$/.test(k));

      setServico(s);
      setSelecionados({
        compressor: chavesDeValores(OPTIONS_COMPRESSOR, s.sub_defeitos_compressor),
        // pontos numerados voltam do texto; "Nao localizado" volta do enum
        vazamento: [...ponto.chaves, ...vazamentoChaves],
        outros: chavesDeValores(OPTIONS_OUTROS, s.sub_defeitos_outros),
        iluminacao: chavesDeValores(OPTIONS_ILUMINACAO, s.sub_defeitos_iluminacao),
        estrutura: chavesDeValores(OPTIONS_ESTRUTURA, s.sub_defeitos_estrutura),
      });
      setDefeitoOutrosDesc(s.defeito_outros_descricao ?? "");
      setVazamentoObservacao(ponto.observacao);
      setMateriais(
        (s.materiais_utilizados ?? []).map((m) => ({
          nome: m.nome,
          quantidade: String(m.quantidade),
          valor: String(m.valor).replace(".", ","),
        }))
      );
    } catch (e) {
      setErroCarga(getErrorMessage(e, "Falha ao carregar o equipamento."));
    } finally {
      setLoading(false);
    }
  }, [chamadoId, visitaId, servicoIdParam]);

  useEffect(() => {
    loadExisting();
  }, [loadExisting]);

  // =====================================================
  // ALTERAR SELEÇÃO DOS MULTISELECTS
  // =====================================================
  function toggle(categoria: CategoriaKey, key: string) {
    setSelecionados((prev) => {
      const atual = prev[categoria];
      let proxima = atual.includes(key) ? atual.filter((k) => k !== key) : [...atual, key];
      // "Nao localizado" exclui os pontos numerados e vice-versa
      if (categoria === "vazamento" && !atual.includes(key)) {
        proxima =
          key === CHAVE_NAO_LOCALIZADO
            ? [CHAVE_NAO_LOCALIZADO]
            : proxima.filter((k) => k !== CHAVE_NAO_LOCALIZADO);
      }
      return { ...prev, [categoria]: proxima };
    });
  }

  function resumo(categoria: CategoriaKey): string {
    const opcoes = OPTIONS_POR_CATEGORIA[categoria];
    const rotulos = selecionados[categoria]
      .map((k) => opcoes.find((o) => o.key === k)?.label)
      .filter(Boolean) as string[];
    if (rotulos.length === 0) return "Nenhum";
    if (categoria === "vazamento" || categoria === "estrutura") {
      return rotulos.map((r) => r.split(" - ")[0]).join(", ");
    }
    return rotulos.join(", ");
  }

  // =====================================================
  // MATERIAIS
  // =====================================================
  function addMaterial() {
    setMateriais((m) => [...m, { nome: "", quantidade: "1", valor: "" }]);
  }

  function removeMaterial(i: number) {
    setMateriais((m) => m.filter((_, idx) => idx !== i));
  }

  function editarMaterial(i: number, campo: keyof MaterialForm, texto: string) {
    setMateriais((prev) => prev.map((x, idx) => (idx === i ? { ...x, [campo]: texto } : x)));
    setErros((e) => ({ ...e, materiais: undefined }));
  }

  // =====================================================
  // SALVAR (PATCH) E SALVAR CONSERTO (PATCH + POST salvar-conserto)
  // =====================================================
  function montarPayload(): { payload: ServicoPatch; ok: boolean } {
    const novosErros: typeof erros = {};

    const materiaisPayload: { nome: string; quantidade: number; valor: number }[] = [];
    for (const m of materiais) {
      const quantidade = /^\d+$/.test(m.quantidade.trim()) ? Number(m.quantidade.trim()) : 0;
      const valor = parseValor(m.valor);
      if (!m.nome.trim() || quantidade < 1 || valor === null) {
        novosErros.materiais =
          "Cada material precisa de nome, quantidade (inteiro, mínimo 1) e valor válido (ex.: 12,50).";
        break;
      }
      materiaisPayload.push({ nome: m.nome.trim(), quantidade, valor });
    }

    const compressor = valoresDeChaves(OPTIONS_COMPRESSOR, selecionados.compressor);
    const vazamento = valoresDeChaves(OPTIONS_VAZAMENTO, selecionados.vazamento);
    const outros = valoresDeChaves(OPTIONS_OUTROS, selecionados.outros);
    const iluminacao = valoresDeChaves(OPTIONS_ILUMINACAO, selecionados.iluminacao);
    const estrutura = valoresDeChaves(OPTIONS_ESTRUTURA, selecionados.estrutura);

    const refrigeracao: string[] = [];
    if (compressor.length) refrigeracao.push("Compressor");
    if (vazamento.length) refrigeracao.push("Vazamento");
    if (outros.length) refrigeracao.push("Outros (Refrigeração)");

    const principais: string[] = [];
    if (refrigeracao.length) principais.push("Refrigeração");
    if (iluminacao.length) principais.push("Iluminação");
    if (estrutura.length) principais.push("Estrutura");
    if (defeitoOutrosDesc.trim()) principais.push("Outros");

    // Somente defeitos, descricoes e materiais: modelo/serie/nome nao sao enviados (422 no servidor).
    const payload: ServicoPatch = {
      defeitos_principais: principais,
      sub_defeitos_refrigeracao: refrigeracao,
      sub_defeitos_compressor: compressor,
      sub_defeitos_vazamento: vazamento,
      sub_defeitos_outros: outros,
      sub_defeitos_iluminacao: iluminacao,
      sub_defeitos_estrutura: estrutura,
      defeito_outros_descricao: defeitoOutrosDesc.trim() || null,
      vazamento_ponto_descricao: comporPontoDescricao(selecionados.vazamento, vazamentoObservacao),
      materiais_utilizados: materiaisPayload,
    };

    setErros(novosErros);
    return { payload, ok: Object.keys(novosErros).length === 0 };
  }

  async function executarSalvar(conserto: boolean) {
    if (savingRef.current || chamadoId === null || visitaId === null || !servico) return;

    const montado = montarPayload();
    if (!montado.ok) return;

    // "Salvar conserto" exige ao menos um defeito principal (o servidor valida de novo: 422).
    if (conserto && montado.payload.defeitos_principais.length === 0) {
      setErros((e) => ({
        ...e,
        defeitos: "Informe ao menos um defeito principal para salvar o conserto.",
      }));
      return;
    }
    setErros((e) => ({ ...e, defeitos: undefined }));

    savingRef.current = true;
    try {
      setSaving(conserto ? "conserto" : "salvar");
      // Grava no aparelho (servico_salvo e, no conserto, conserto_salvo) e envia depois.
      const ctx = { idOs: chamadoId, idVisita: visitaId };
      if (conserto) {
        await salvarConserto(ctx, servico.id_servico, montado.payload);
        setServico((atual) => ({ ...(atual ?? servico), conserto_salvo_em: new Date().toISOString() }));
      } else {
        await salvarRegistroServico(ctx, servico.id_servico, montado.payload);
      }

      Alert.alert(
        conserto ? "Conserto salvo" : "Alterações salvas",
        "Salvo no aparelho; será enviado quando houver conexão."
      );
      if (conserto) voltarParaOS(router, chamadoId);
    } catch (err) {
      // Todos os campos permanecem preenchidos para nova tentativa.
      alertError(err, conserto ? "Falha ao salvar o conserto." : "Falha ao salvar o registro.");
    } finally {
      savingRef.current = false;
      setSaving(null);
    }
  }

  // =====================================================
  // ESTADOS DE TELA
  // =====================================================
  if (chamadoId === null || visitaId === null || servicoIdParam === null) {
    return (
      <View style={{ flex: 1 }}>
        <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />
        <View style={{ flex: 1, justifyContent: "center", padding: 24 }}>
          <Text style={{ color: colors.red[900], textAlign: "center" }}>
            OS, visita ou equipamento não identificados. Volte e tente novamente.
          </Text>
        </View>
      </View>
    );
  }

  if (loading || erroCarga) {
    return (
      <View style={{ flex: 1 }}>
        <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />
        <View style={{ flex: 1, justifyContent: "center", alignItems: "center", padding: 24, gap: 16 }}>
          {loading ? (
            <ActivityIndicator size="large" />
          ) : (
            <>
              <Text style={{ color: colors.red[900], textAlign: "center" }}>{erroCarga}</Text>
              <Button title="Tentar novamente" onPress={loadExisting} />
            </>
          )}
        </View>
      </View>
    );
  }

  const modeloExibido = servico?.modelo || servico?.nome_equipamento || "Modelo não informado";
  const serieExibida = servico?.numero_serie || servico?.numero_serie_atendido || "S/N";
  const ocupado = saving !== null;

  const cabecalho = (texto: string) => (
    <Text
      style={{
        color: "#fff",
        fontSize: 15,
        padding: 6,
        backgroundColor: colors.blue[900],
      }}
    >
      {texto}
    </Text>
  );

  const linha = (categoria: CategoriaKey) => (
    <SectionRow
      label={TITULO_CATEGORIA[categoria]}
      value={resumo(categoria)}
      onPress={() => setCategoriaAberta(categoria)}
    />
  );

  // =====================================================
  // RENDER
  // =====================================================
  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: "#fff" }}
    >
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />

      <ScrollView style={{ padding: 12 }} keyboardShouldPersistTaps="handled">
        <Text style={{ fontSize: 18, fontWeight: "700", marginBottom: 12, color: colors.blue[900] }}>
          Registro do atendimento
        </Text>

        {/* Equipamento da OS: somente leitura (definido pelo escritório). */}
        <View
          style={{
            padding: 12,
            marginBottom: 8,
            backgroundColor: colors.gray[100],
            borderRadius: 8,
            borderLeftWidth: 4,
            borderLeftColor: colors.blue[900],
          }}
        >
          <Text style={{ color: colors.blue[900], fontSize: 16, fontWeight: "700", marginBottom: 4 }}>
            {modeloExibido}
          </Text>
          <Text style={{ color: colors.gray[800], fontSize: 14 }}>Número de série: {serieExibida}</Text>
          <Text style={{ color: colors.gray[800], fontSize: 14, marginTop: 4 }}>
            Conserto: {servico?.conserto_salvo_em ? "salvo" : "ainda não salvo"}
          </Text>
        </View>

        <Text style={{ paddingTop: 12, paddingBottom: 10, fontSize: 18, fontWeight: "700" }}>
          Defeitos
        </Text>
        {erros.defeitos ? (
          <Text style={{ color: colors.red[900], fontSize: 13, marginBottom: 8 }}>{erros.defeitos}</Text>
        ) : null}

        {cabecalho("Refrigeração")}
        {linha("compressor")}
        {linha("vazamento")}
        {linha("outros")}

        {cabecalho("Iluminação")}
        {linha("iluminacao")}

        {cabecalho("Estrutura")}
        {linha("estrutura")}

        {/* ===================================================== */}
        {/* CAMPOS DE TEXTO */}
        {/* ===================================================== */}

        <View style={{ marginTop: 12 }}>
          <Text style={{ fontWeight: "700" }}>Descrição (outros defeitos)</Text>
          <TextInput
            placeholder="Descrição de defeitos não listados..."
            value={defeitoOutrosDesc}
            onChangeText={setDefeitoOutrosDesc}
            multiline
            style={{
              minHeight: 80,
              borderWidth: 1,
              borderColor: colors.gray[200],
              padding: 8,
              marginTop: 8,
              borderRadius: 6,
              textAlignVertical: "top",
            }}
          />
        </View>

        <View style={{ marginTop: 12 }}>
          <Text style={{ fontWeight: "700" }}>Observação do ponto do vazamento</Text>
          <TextInput
            placeholder="Local do vazamento..."
            value={vazamentoObservacao}
            onChangeText={setVazamentoObservacao}
            multiline
            style={{
              minHeight: 60,
              borderWidth: 1,
              borderColor: colors.gray[200],
              padding: 8,
              marginTop: 8,
              borderRadius: 6,
              textAlignVertical: "top",
            }}
          />
        </View>

        {/* ===================================================== */}
        {/* MATERIAIS */}
        {/* ===================================================== */}

        <View style={{ marginTop: 20 }}>
          <Text style={{ fontSize: 18, fontWeight: "700" }}>Materiais Utilizados</Text>

          {materiais.map((m, idx) => (
            <View
              key={idx}
              style={{
                marginTop: 8,
                borderWidth: 1,
                borderColor: colors.gray[200],
                padding: 8,
                borderRadius: 6,
              }}
            >
              <TextInput
                placeholder="Nome do material"
                value={m.nome}
                onChangeText={(t) => editarMaterial(idx, "nome", t)}
                style={{ minHeight: 44 }}
              />

              <View style={{ flexDirection: "row", gap: 8, marginTop: 8, alignItems: "center" }}>
                <Text>Qtd:</Text>
                <TextInput
                  placeholder="1"
                  keyboardType="numeric"
                  value={m.quantidade}
                  onChangeText={(t) => editarMaterial(idx, "quantidade", t.replace(/\D/g, ""))}
                  style={{
                    flex: 1,
                    minHeight: 44,
                    borderBottomWidth: 1,
                    borderColor: colors.gray[200],
                  }}
                />
                <Text>Valor (R$):</Text>
                <TextInput
                  placeholder="0,00"
                  keyboardType="decimal-pad"
                  value={m.valor}
                  onChangeText={(t) => editarMaterial(idx, "valor", t.replace(/[^0-9.,]/g, ""))}
                  style={{
                    flex: 1,
                    minHeight: 44,
                    borderBottomWidth: 1,
                    borderColor: colors.gray[200],
                  }}
                />
              </View>

              <View style={{ marginTop: 8, alignItems: "flex-end" }}>
                <Button title="Remover" variant="secondary" onPress={() => removeMaterial(idx)} />
              </View>
            </View>
          ))}

          {erros.materiais ? (
            <Text style={{ color: colors.red[900], fontSize: 13, marginTop: 8 }}>{erros.materiais}</Text>
          ) : null}

          <View style={{ marginTop: 8 }}>
            <Button title="Adicionar material" variant="secondary" onPress={addMaterial} />
          </View>
        </View>

        {/* ===================================================== */}
        {/* IMAGENS DE REFERENCIA */}
        {/* ===================================================== */}

        <View style={{ marginTop: 20 }}>
          <Text style={{ fontSize: 18, fontWeight: "700" }}>Pontos de solda</Text>
          <Image
            source={Pontos_solda}
            resizeMode="contain"
            style={{ width: "100%", height: undefined, aspectRatio: 2, marginVertical: 10 }}
          />

          <Text style={{ fontSize: 18, fontWeight: "700" }}>Pontos da estrutura</Text>
          <Image
            source={Pontos_estrutura}
            resizeMode="contain"
            style={{ width: "100%", height: undefined, aspectRatio: 2, marginVertical: 20 }}
          />
        </View>

        {/* ===================================================== */}
        {/* BOTÃO SALVAR */}
        {/* ===================================================== */}
        <View style={{ marginTop: 20, marginBottom: 40, gap: 12 }}>
          <Button
            title="Salvar alterações"
            variant="secondary"
            onPress={() => executarSalvar(false)}
            loading={saving === "salvar"}
            disabled={ocupado}
            width="100%"
          />
          <Button
            title="Salvar conserto"
            onPress={() => executarSalvar(true)}
            loading={saving === "conserto"}
            disabled={ocupado}
            width="100%"
          />
        </View>
      </ScrollView>

      {/* ===================================================== */}
      {/* MODAL DE SELEÇÃO */}
      {/* ===================================================== */}
      {categoriaAberta && (
        <MultiSelectModal
          visible
          options={OPTIONS_POR_CATEGORIA[categoriaAberta]}
          selected={selecionados[categoriaAberta]}
          onToggle={(key) => toggle(categoriaAberta, key)}
          onClose={() => setCategoriaAberta(null)}
          title={`Selecionar: ${TITULO_CATEGORIA[categoriaAberta]}`}
        />
      )}
    </KeyboardAvoidingView>
  );
}

// =====================================================
// COMPONENTE DE LINHA DE SEÇÃO
// =====================================================
function SectionRow({
  label,
  onPress,
  value,
}: {
  label: string;
  onPress: () => void;
  value?: string;
}) {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={{
        minHeight: 52,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderColor: colors.gray[200],
        flexDirection: "row",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <Text style={{ fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: colors.gray[500], maxWidth: "60%", textAlign: "right" }}>{value}</Text>
    </TouchableOpacity>
  );
}
