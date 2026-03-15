// src/app/detalheChamado/RegistroDefeito.tsx
import React, { useEffect, useState, useCallback } from "react";
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
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { Header } from "@/components/header/indexHeader";
import { listarServicos, criarServico, atualizarServico } from "@/api/servico";
import { Button } from "@/components/button/indexButton";

import Pontos_solda from "../../../assets/images/pontos_solda.png";
import Pontos_estrutura from "../../../assets/images/pontos_estrutura.png";

// =====================================================
// TIPOS
// =====================================================
type Option = { key: string; label: string };

// =====================================================
// OPTIONS (ARRAYS PARA O MODAL)
// =====================================================

const OPTIONS_COMPRESSOR: Option[] = [
  { key: "queimado", label: "Queimado" },
  { key: "em_massa", label: "Em Massa" },
  { key: "em_curto", label: "Em Curto" },
  { key: "corrente_alta", label: "Corrente Alta" },
  { key: "nao_parte", label: "Não Parte" },
  { key: "sem_compressao", label: "Sem Compressão" },
  { key: "travado", label: "Travado" },
  { key: "com_barulho", label: "Com Barulho" },
  { key: "nao_succiona", label: "Não Succiona" },
  { key: "desarmando", label: "Desarmado" },
];

const MAP_COMPRESSOR: Record<string, string> = OPTIONS_COMPRESSOR.reduce(
  (acc, item) => ({ ...acc, [item.key]: item.label }),
  {}
);

const OPTIONS_VAZAMENTO: Option[] = [
  { key: "1", label: "1 - Solda - Prata 30% (Aço / Aço)" },
  { key: "2", label: "2 - Solda - Prata 30% (Cobre / Aço)" },
  { key: "3", label: "3 - Tampão Lokring (Cobre)" },
  { key: "4", label: "4 - Solda - Prata 30% (Aço / Cobre)" },
  { key: "5", label: "5 - União Lokring (Cobre / Alumínio)" },
  { key: "6", label: "6 - União Lokring (Alumínio / Cobre)" },
  { key: "7", label: "7 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { key: "8", label: "8 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { key: "9", label: "9 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { key: "10", label: "10 - Solda - Prata 30% (Cobre / Aço)" },
  { key: "11", label: "11 - Solda - Prata 30% (Cobre / Aço)" },
  { key: "12", label: "12 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { key: "13", label: "13 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { key: "14", label: "14 - Solda - Prata 30% (Cobre / Aço)" },
  { key: "15", label: "15 - Solda - Prata 30% (Cobre / Aço)" },
  { key: "16", label: "16 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { key: "17", label: "17 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { key: "18", label: "Não localizado" },
];

const OPTIONS_OUTROS: Option[] = [
  { key: "filtro_entupido", label: "Filtro Entupido" },
  { key: "capilar_obstruido", label: "Capilar Obstruído" },
  { key: "micromotor_queimado", label: "Micromotor Queimado" },
  { key: "micromotor_travado", label: "Micromotor Travado" },
  { key: "controlador_queimado", label: "Controlador Queimado" },
  { key: "regulagem_parametros", label: "Regulagem Parâmetros" },
];

const OPTIONS_ILUMINACAO: Option[] = [
  { key: "lampada_queimada", label: "Lâmpada Queimada" },
  { key: "sem_alimentacao", label: "Sem Alimentação" },
  { key: "em_curto", label: "Em Curto" },
];

const OPTIONS_ESTRUTURA: Option[] = [
  { key: "1", label: "1 - Perfil Curvo Vidro" },
  { key: "2", label: "2 - Perfil Suporte Iluminação" },
  { key: "3", label: "3 - Lente Calha Iluminação" },
  { key: "4", label: "4 - Perfil Vedação" },
  { key: "5", label: "5 - Perfil Porta Etiqueta" },
  { key: "6", label: "6 - Puxador" },
  { key: "7", label: "7 - Porta Parachoque" },
  { key: "8", label: "8 - Canto 90°" },
  { key: "9", label: "9 - Acrílico Carel" },
  { key: "10", label: "10 - Perfil Frontal" },
  { key: "11", label: "11 - Parachoque Frontal" },
  { key: "12", label: "12 - Parachoque Lateral" },
];

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
    <Modal visible={visible} transparent animationType="slide">
      <View
        style={{
          flex: 1,
          backgroundColor: "rgba(0,0,0,0.4)",
          justifyContent: "center",
        }}
      >
        <View
          style={{
            margin: 20,
            backgroundColor: "#fff",
            borderRadius: 8,
            maxHeight: "80%",
            padding: 12,
          }}
        >
          <Text style={{ fontWeight: "700", fontSize: 16, marginBottom: 8 }}>
            {title}
          </Text>

          <FlatList
            data={options}
            keyExtractor={(i) => i.key}
            renderItem={({ item }) => {
              const isSelected = selected.includes(item.key);

              return (
                <Pressable
                  onPress={() => onToggle(item.key)}
                  style={{
                    paddingVertical: 10,
                    flexDirection: "row",
                    alignItems: "center",
                  }}
                >
                  <View
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: 4,
                      borderWidth: 1,
                      borderColor: "#666",
                      justifyContent: "center",
                      alignItems: "center",
                      marginRight: 10,
                    }}
                  >
                    {isSelected && (
                      <View
                        style={{
                          width: 12,
                          height: 12,
                          backgroundColor: "#333",
                        }}
                      />
                    )}
                  </View>

                  <Text>{item.label}</Text>
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
  const params = useLocalSearchParams();
  const router = useRouter();

  const chamadoId = Number(params.chamadoId);
  const visitaId = Number(params.visitaId);
  const servicoId = params.servicoId ? Number(params.servicoId) : undefined;
  const numeroSerie = String(params.numeroSerie ?? "");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [servico, setServico] = useState<any | null>(null);

  // States dos seletores
  const [compressorSel, setCompressorSel] = useState<string[]>([]);
  const [vazamentoSel, setVazamentoSel] = useState<string[]>([]);
  const [outrosSel, setOutrosSel] = useState<string[]>([]);
  const [iluminacaoSel, setIluminacaoSel] = useState<string[]>([]);
  const [estruturaSel, setEstruturaSel] = useState<string[]>([]);

  const [defeitoOutrosDesc, setDefeitoOutrosDesc] = useState("");
  const [vazamentoPontoDesc, setVazamentoPontoDesc] = useState("");

  const [materiais, setMateriais] = useState<
    { nome: string; quantidade: number; valor: number }[]
  >([]);

  const [modalOpen, setModalOpen] = useState<{
    key: string | null;
    open: boolean;
  }>({ key: null, open: false });

  // =====================================================
  // CARREGAR SERVIÇO EXISTENTE
  // =====================================================
  const loadExisting = useCallback(async () => {
    try {
      setLoading(true);

      const lista = await listarServicos(chamadoId, visitaId);
      let s = null;

      if (servicoId)
        s = lista.find((x: any) => x.id_servico === servicoId);
      else if (numeroSerie)
        s = lista.find(
          (x: any) => x.numero_serie_atendido === numeroSerie
        );

      if (s) {
        setServico(s);
        setCompressorSel(s.sub_defeitos_compressor || []);
        setVazamentoSel(s.sub_defeitos_vazamento || []);
        setOutrosSel(s.sub_defeitos_outros || []);
        setIluminacaoSel(s.sub_defeitos_iluminacao || []);
        setEstruturaSel(s.sub_defeitos_estrutura || []);
        setDefeitoOutrosDesc(s.defeito_outros_descricao || "");
        setVazamentoPontoDesc(s.vazamento_ponto_descricao || "");
        setMateriais(s.materiais_utilizados || []);
      } else {
        setServico(null);
      }
    } catch (e) {
      console.log("Erro carregar servicos", e);
      Alert.alert("Erro", "Falha ao carregar serviço.");
    } finally {
      setLoading(false);
    }
  }, [chamadoId, visitaId, servicoId, numeroSerie]);

  useEffect(() => {
    loadExisting();
  }, [loadExisting]);

  // =====================================================
  // ALTERAR SELEÇÃO DOS MULTISELECTS
  // =====================================================
  function toggleSel(setter: (v: string[]) => void, arr: string[], key: string) {
    const copy = [...arr];
    const index = copy.indexOf(key);
    index >= 0 ? copy.splice(index, 1) : copy.push(key);
    setter(copy);
  }

  // =====================================================
  // ADICIONAR / REMOVER MATERIAIS
  // =====================================================
  function addMaterial() {
    setMateriais((m) => [...m, { nome: "", quantidade: 1, valor: 0 }]);
  }

  function removeMaterial(i: number) {
    setMateriais((m) => m.filter((_, idx) => idx !== i));
  }

  // =====================================================
  // SALVAR SERVIÇO
  // =====================================================
  async function handleSalvar() {
    try {
      setSaving(true)

      const payload = {
        numero_serie_atendido:
          numeroSerie || servico?.numero_serie_atendido || null,
        
        nome_equipamento: servico?.nome_equipamento || "Equipamento",

        defeitos_principais: [],

        sub_defeitos_compressor: compressorSel.map(
          (k) => MAP_COMPRESSOR[k]
        ),

        sub_defeitos_vazamento: vazamentoSel,
        sub_defeitos_outros: outrosSel,
        sub_defeitos_iluminacao: iluminacaoSel,
        sub_defeitos_estrutura: estruturaSel,

        defeito_outros_descricao: defeitoOutrosDesc || null,
        vazamento_ponto_descricao: vazamentoPontoDesc || null,

        materiais_utilizados: materiais.map((m) => ({
          nome: m.nome,
          quantidade: Number(m.quantidade),
          valor: Number(m.valor),
        })),
      };

      console.log("PAYLOAD ENVIADO:", payload);

      if (servico?.id_servico) {
        const updated = await atualizarServico(
          chamadoId,
          visitaId,
          servico.id_servico,
          payload
        );
        setServico(updated);
        Alert.alert("Sucesso", "Serviço atualizado.");
      } else {
        const created = await criarServico(chamadoId, visitaId, payload);
        setServico(created);
        Alert.alert("Sucesso", "Serviço criado.");
      }

      await loadExisting();
    } catch (err: any) {

  const detail = err?.response?.data?.detail;

  const msg =
    Array.isArray(detail)
      ? detail.map((d: any) => d.msg || JSON.stringify(d)).join("\n")
      : typeof detail === "string"
      ? detail
      : JSON.stringify(detail, null, 2);

  Alert.alert("Erro", msg || "Erro desconhecido");
}
finally {
      setSaving(false);
    }
  }

  // =====================================================
  // TELA LOADING
  // =====================================================
  if (loading) {
    return (
      <View style={{ flex: 1 }}>
        <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />
        <View
          style={{
            flex: 1,
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          <ActivityIndicator size="large" />
        </View>
      </View>
    );
  }

  // =====================================================
  // RENDER
  // =====================================================
  return (
    <View style={{ flex: 1 }}>
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.back()} />

      <ScrollView style={{ padding: 12 }}>
        <Text style={{ fontSize: 18, fontWeight: "700", marginBottom: 8 }}>
          Nome do equipamento
        </Text>
        <Text style={{ marginBottom: 6 }}>
          Número de série:{" "}
          {numeroSerie || servico?.numero_serie_atendido || "—"}
        </Text>

        {/* ===================================================== */}
        {/* SEÇÕES DE DEFEITOS */}
        {/* ===================================================== */}

        <Text
          style={{
            paddingTop: 20,
            paddingBottom: 10,
            fontSize: 18,
            fontWeight: "700",
          }}
        >
          Defeitos
        </Text>

        <Text
          style={{
            color: "#fff",
            fontSize: 15,
            padding: 5,
            backgroundColor: "#194869",
          }}
        >
          Refrigeração
        </Text>

        <SectionRow
          label="Compressor"
          value={compressorSel.join(", ") || "Nenhum"}
          onPress={() => setModalOpen({ key: "compressor", open: true })}
        />

        <SectionRow
          label="Vazamento"
          value={vazamentoSel.join(", ") || "Nenhum"}
          onPress={() => setModalOpen({ key: "vazamento", open: true })}
        />

        <SectionRow
          label="Outros"
          value={outrosSel.join(", ") || "Nenhum"}
          onPress={() => setModalOpen({ key: "outros", open: true })}
        />

        <Text
          style={{
            color: "#fff",
            fontSize: 15,
            padding: 5,
            backgroundColor: "#194869",
          }}
        >
          Iluminação
        </Text>

        <SectionRow
          label="Iluminação"
          value={iluminacaoSel.join(", ") || "Nenhum"}
          onPress={() => setModalOpen({ key: "iluminacao", open: true })}
        />

        <Text
          style={{
            color: "#fff",
            fontSize: 15,
            padding: 5,
            backgroundColor: "#194869",
          }}
        >
          Estrutura
        </Text>

        <SectionRow
          label="Estrutura"
          value={estruturaSel.join(", ") || "Nenhum"}
          onPress={() => setModalOpen({ key: "estrutura", open: true })}
        />

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
              borderColor: "#ddd",
              padding: 8,
              marginTop: 8,
              borderRadius: 6,
            }}
          />
        </View>

        <View style={{ marginTop: 12 }}>
          <Text style={{ fontWeight: "700" }}>
            Descrição do ponto do vazamento
          </Text>
          <TextInput
            placeholder="Local do vazamento..."
            value={vazamentoPontoDesc}
            onChangeText={setVazamentoPontoDesc}
            multiline
            style={{
              minHeight: 60,
              borderWidth: 1,
              borderColor: "#ddd",
              padding: 8,
              marginTop: 8,
              borderRadius: 6,
            }}
          />
        </View>

        {/* ===================================================== */}
        {/* MATERIAIS */}
        {/* ===================================================== */}

        <View style={{ marginTop: 20 }}>
          <Text style={{ fontSize: 18, fontWeight: "700" }}>
            Materiais Utilizados
          </Text>

          {materiais.map((m, idx) => (
            <View
              key={idx}
              style={{
                marginTop: 8,
                borderWidth: 1,
                borderColor: "#eee",
                padding: 8,
                borderRadius: 6,
              }}
            >
              <TextInput
                placeholder="Nome do material"
                value={m.nome}
                onChangeText={(t) =>
                  setMateriais((prev) =>
                    prev.map((x, i) =>
                      i === idx ? { ...x, nome: t } : x
                    )
                  )
                }
              />

              <View style={{ flexDirection: "row", gap: 8, marginTop: 8 }}>
                <Text>Quantidade:</Text>
                <TextInput
                  placeholder="Qtd"
                  keyboardType="numeric"
                  value={String(m.quantidade)}
                  onChangeText={(t) =>
                    setMateriais((prev) =>
                      prev.map((x, i) =>
                        i === idx
                          ? { ...x, quantidade: Number(t || 0) }
                          : x
                      )
                    )
                  }
                  style={{ flex: 1 }}
                />
                <Text>Valor:</Text>
                <TextInput
                  placeholder="Valor"
                  keyboardType="numeric"
                  value={String(m.valor)}
                  onChangeText={(t) =>
                    setMateriais((prev) =>
                      prev.map((x, i) =>
                        i === idx ? { ...x, valor: Number(t || 0) } : x
                      )
                    )
                  }
                  style={{ flex: 1 }}
                />
              </View>

              <View style={{ marginTop: 8, alignItems: "flex-end" }}>
                <Button title="Remover" onPress={() => removeMaterial(idx)} />
              </View>
            </View>
          ))}

          <View style={{ marginTop: 8 }}>
            <Button title="Adicionar material" onPress={addMaterial} />
          </View>
        </View>

        {/* ===================================================== */}
        {/* IMAGENS */}
        {/* ===================================================== */}

        <View style={{ marginTop: 20 }}>
          <Text style={{ fontSize: 18, fontWeight: "700" }}>
            Pontos de solda
          </Text>
          <Image
            source={Pontos_solda}
            resizeMode="contain"
            style={{
              width: "100%",
              height: undefined,
              aspectRatio: 2,
              marginVertical: 10,
            }}
          />

          <Text style={{ fontSize: 18, fontWeight: "700" }}>
            Pontos da estrutura
          </Text>
          <Image
            source={Pontos_estrutura}
            resizeMode="contain"
            style={{
              width: "100%",
              height: undefined,
              aspectRatio: 2,
              marginVertical: 20,
            }}
          />
        </View>

        {/* ===================================================== */}
        {/* BOTÃO SALVAR */}
        {/* ===================================================== */}
        <View style={{ marginTop: 20, marginBottom: 40 }}>
          <Button
            title={saving ? "Salvando..." : "Salvar"}
            onPress={handleSalvar}
            disabled={saving}
          />
        </View>
      </ScrollView>

      {/* ===================================================== */}
      {/* MODAL DE SELEÇÃO */}
      {/* ===================================================== */}
      {modalOpen.open && modalOpen.key && (
        <MultiSelectModal
          visible={modalOpen.open}
          options={
            modalOpen.key === "compressor"
              ? OPTIONS_COMPRESSOR
              : modalOpen.key === "vazamento"
              ? OPTIONS_VAZAMENTO
              : modalOpen.key === "outros"
              ? OPTIONS_OUTROS
              : modalOpen.key === "iluminacao"
              ? OPTIONS_ILUMINACAO
              : OPTIONS_ESTRUTURA
          }
          selected={
            modalOpen.key === "compressor"
              ? compressorSel
              : modalOpen.key === "vazamento"
              ? vazamentoSel
              : modalOpen.key === "outros"
              ? outrosSel
              : modalOpen.key === "iluminacao"
              ? iluminacaoSel
              : estruturaSel
          }
          onToggle={(key) => {
            if (modalOpen.key === "compressor")
              toggleSel(setCompressorSel, compressorSel, key);
            if (modalOpen.key === "vazamento")
              toggleSel(setVazamentoSel, vazamentoSel, key);
            if (modalOpen.key === "outros")
              toggleSel(setOutrosSel, outrosSel, key);
            if (modalOpen.key === "iluminacao")
              toggleSel(setIluminacaoSel, iluminacaoSel, key);
            if (modalOpen.key === "estrutura")
              toggleSel(setEstruturaSel, estruturaSel, key);
          }}
          onClose={() => setModalOpen({ key: null, open: false })}
          title={`Selecionar ${modalOpen.key}`}
        />
      )}
    </View>
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
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderColor: "#eee",
        flexDirection: "row",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <Text style={{ fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: "#666", maxWidth: "60%", textAlign: "right" }}>
        {value}
      </Text>
    </TouchableOpacity>
  );
}
