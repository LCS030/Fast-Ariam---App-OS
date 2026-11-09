// File: src/app/detalheChamado/[id].tsx
import React, { useState, useMemo, useCallback, useRef } from "react";
import { View, Text, ScrollView, ActivityIndicator, Alert, Linking } from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";

import { Header } from "@/components/header/indexHeader";
import { CardEquipamento, EquipamentoItem } from "@/components/CardEquipamento/indexCardEquipamento";
import { EquipamentoPickerModal } from "@/components/EquipamentoPickerModal/indexEquipamentoPickerModal";
import { PausaModal } from "@/components/PausaModal/indexPausaModal";
import { SeloAcao } from "@/components/SeloAcao/indexSeloAcao";
import { Button } from "@/components/button/indexButton";
import type { Chamado } from "@/api/chamado";
import type { Cliente } from "@/api/cliente";
import type { EquipamentoEstado } from "@/api/visitas";
import { alertError, getErrorMessage } from "@/utils/alerts";
import { formatDateTime } from "@/utils/formatDate";
import { irParaPendencias } from "@/utils/nav";
import { paramNum } from "@/utils/params";
import { derivarUi } from "@/utils/visita";
import { obterClienteComCache } from "@/offline/clienteCache";
import { listarAcoesDaOs, obterOsLocal, OsLocal, ultimaAtualizacaoCache } from "@/offline/cacheOS";
import { registrarInicioAtendimento, registrarPausa } from "@/offline/acoes";
import { sincronizar } from "@/offline/sync";
import { useStatusOffline, useVersaoLocal } from "@/offline/store";
import { EventoOutbox, MOTIVO_CODIGO, ROTULO_EVENTO } from "@/offline/tipos";
import { styles } from "@/styles/styleDetalheChamado";
import { colors } from "@/styles/Colors";

type TipoFoto = "defeito" | "conserto";

const MAX_ACOES_LISTADAS = 8;

export default function DetalheChamadoScreen() {
  const params = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();

  const idNum = paramNum(params.id);

  const versao = useVersaoLocal(); // muda quando o cache ou a fila mudam
  const statusOffline = useStatusOffline();

  const [os, setOs] = useState<OsLocal | null>(null);
  const [acoes, setAcoes] = useState<EventoOutbox[]>([]);
  const [cliente, setCliente] = useState<Cliente | null>(null);
  const [clienteErro, setClienteErro] = useState(false);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  // OS que nao esta mais no cache depois de sincronizar: reatribuida, cancelada ou removida.
  const [indisponivel, setIndisponivel] = useState(false);
  const [sincronizando, setSincronizando] = useState(false);
  const [executando, setExecutando] = useState(false);
  const executandoRef = useRef(false); // trava sincrona contra duplo toque
  const [showPausaModal, setShowPausaModal] = useState(false);
  const [fotoPendente, setFotoPendente] = useState<TipoFoto | null>(null); // abre o seletor de equipamento

  // Tudo vem do aparelho (cache do servidor + acoes ainda nao enviadas), mesmo sem internet.
  const carregar = useCallback(async () => {
    if (idNum === null || idNum <= 0) {
      setErro("Identificador do chamado inválido.");
      setLoading(false);
      return;
    }

    try {
      const local = await obterOsLocal(idNum);
      if (!local) {
        const nunca = (await ultimaAtualizacaoCache()) === null;
        setOs(null);
        setAcoes([]);
        setIndisponivel(!nunca);
        setErro(
          nunca
            ? "Esta OS ainda não foi baixada para o aparelho. Conecte-se à internet e sincronize."
            : "Esta OS não está mais disponível para você. Ela pode ter sido reatribuída, cancelada ou removida. Volte à lista para ver as OS atuais."
        );
      } else {
        setOs(local);
        setAcoes(await listarAcoesDaOs(idNum));
        setErro(null);
        setIndisponivel(false);
      }
    } catch (err) {
      setErro(getErrorMessage(err, "Falha ao ler a OS salva no aparelho."));
    } finally {
      setLoading(false);
    }
    // `versao` refaz a leitura quando o cache ou a fila mudam.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idNum, versao]);

  async function sincronizarAgora() {
    setSincronizando(true);
    try {
      await sincronizar();
    } finally {
      setSincronizando(false);
      setLoading(true);
      await carregar();
    }
  }

  // Recarrega ao abrir, ao voltar ao foco e quando os dados locais mudam.
  useFocusEffect(
    useCallback(() => {
      carregar();
    }, [carregar])
  );

  const chamado: Chamado | null = os?.chamado ?? null;
  const estado = os?.estado ?? null;
  const visita = os?.visita;
  const idCliente = chamado?.id_cliente;

  // Dados do cliente (endereco): online via GET /clientes/{id}, offline pela copia local.
  // Falha nao bloqueia o fluxo da OS.
  useFocusEffect(
    useCallback(() => {
      if (!idCliente || cliente) return;
      let ativo = true;
      obterClienteComCache(idCliente)
        .then((c) => {
          if (ativo) {
            setCliente(c);
            setClienteErro(false);
          }
        })
        .catch(() => {
          if (ativo) setClienteErro(true);
        });
      return () => {
        ativo = false;
      };
    }, [idCliente, cliente])
  );

  // Passadas 24 h sem login online, novas acoes ficam bloqueadas (RN-39); a OS segue consultavel.
  const bloqueada =
    statusOffline.situacaoSessao === "offline_expirada" ||
    statusOffline.situacaoSessao === "sem_sessao";

  const ui = useMemo(() => {
    if (!chamado) return null;
    const base = derivarUi(chamado, estado);
    if (!bloqueada) return base;
    return {
      ...base,
      acao: null,
      textoAcao: "",
      podePausar: false,
      podeFotoDefeito: false,
      podeRegistrarConserto: false,
      visitaAberta: false,
      mostrarBotoesAtendimento: false,
      podeIniciarAtendimento: false,
      podeFinalizarAtendimento: false,
    };
  }, [chamado, estado, bloqueada]);

  // Equipamentos da OS: SOMENTE LEITURA (o tecnico nao cadastra nem edita).
  // Itens do estado trazem id_servico (ancora de foto/registro) e o progresso por equipamento.
  const itensEstado: EquipamentoEstado[] = useMemo(() => estado?.equipamentos ?? [], [estado]);

  // Lista exibida: a do estado (com progresso) ou, sem ela (visita encerrada), a da propria OS.
  const equipamentosExibidos: EquipamentoItem[] = useMemo(
    () =>
      itensEstado.length > 0
        ? itensEstado
        : (chamado?.equipamentos ?? []).map((e) => ({
            modelo: e.modelo,
            numero_serie: e.numero_serie,
          })),
    [itensEstado, chamado]
  );

  const enderecoFormatado = useMemo(() => {
    if (!cliente) return { linha1: "", linha2: "" };
    const { endereco, numero, bairro, cidade, uf } = cliente;
    const linha1 = endereco
      ? `${endereco}${numero ? ", " + numero : ""}${bairro ? " - " + bairro : ""}`
      : "";
    const linha2 = cidade ? `${cidade}${uf ? " - " + uf : ""}` : "";
    return { linha1, linha2 };
  }, [cliente]);

  const temEndereco = !!(enderecoFormatado.linha1 || enderecoFormatado.linha2);

  async function abrirNoMapa() {
    const consulta = [enderecoFormatado.linha1, enderecoFormatado.linha2].filter(Boolean).join(", ");
    try {
      await Linking.openURL(`geo:0,0?q=${encodeURIComponent(consulta)}`);
    } catch {
      Alert.alert("Mapa indisponível", "Não foi possível abrir um aplicativo de mapas neste aparelho.");
    }
  }

  if (loading) {
    return (
      <View style={styles.loader}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  if (!chamado || !ui || !os) {
    return (
      <View style={{ flex: 1 }}>
        <Header leftIconName="arrow-back" onLeftIconPress={() => router.replace("/Home/indexHome")} />
        <View style={[styles.loader, { padding: 24 }]}>
          <Text style={{ color: colors.red[900], textAlign: "center", marginBottom: 16 }}>
            {erro ?? "Chamado não encontrado."}
          </Text>
          {indisponivel ? (
            <Button title="Voltar à lista" onPress={() => router.replace("/Home/indexHome")} />
          ) : (
            <Button
              title="Sincronizar agora"
              loading={sincronizando}
              onPress={sincronizarAgora}
            />
          )}
        </View>
      </View>
    );
  }

  const osAtual: Chamado = chamado;
  const idOs = osAtual.id_os;

  function irPara(
    pathname:
      | "/detalheChamado/DeslocamentoInicio"
      | "/detalheChamado/DeslocamentoFim"
      | "/detalheChamado/Assinatura",
    extra: Record<string, string> = {}
  ) {
    if (!visita) return;
    router.push({
      pathname,
      params: { chamadoId: String(idOs), visitaId: String(visita.id_visita), ...extra },
    });
  }

  async function handleAcaoPrincipal() {
    if (!visita || !ui || !ui.acao || executando) return;

    switch (ui.acao) {
      case "iniciar_ida":
        irPara("/detalheChamado/DeslocamentoInicio", { tipo: "ida" });
        return;
      case "finalizar_ida":
        irPara("/detalheChamado/DeslocamentoFim", {
          tipo: "ida",
          kmReferencia: os?.kmInicio.ida != null ? String(os.kmInicio.ida) : "",
        });
        return;
      case "iniciar_volta":
        irPara("/detalheChamado/DeslocamentoInicio", { tipo: "volta" });
        return;
      case "finalizar_volta":
        irPara("/detalheChamado/DeslocamentoFim", {
          tipo: "volta",
          kmReferencia: os?.kmInicio.volta != null ? String(os.kmInicio.volta) : "",
        });
        return;
    }
  }

  async function handleIniciarAtendimento() {
    if (!visita || !ui?.podeIniciarAtendimento || executandoRef.current) return;
    executandoRef.current = true;
    try {
      setExecutando(true);
      // Grava no aparelho primeiro; o envio acontece em segundo plano (AR-04).
      await registrarInicioAtendimento({ idOs, idVisita: visita.id_visita });
      Alert.alert("Atendimento iniciado", "Ação salva no aparelho. Será enviada ao servidor assim que houver conexão.");
    } catch (err) {
      // Pendencia local (ex.: falta foto do defeito) ou sessao: a mensagem ja diz o que fazer.
      alertError(err, "Erro ao iniciar atendimento.");
    } finally {
      executandoRef.current = false;
      setExecutando(false);
    }
  }

  function handleFinalizarAtendimento() {
    // A finalizacao (nome, CPF e assinatura) ocorre na tela de assinatura.
    if (!ui?.podeFinalizarAtendimento || executandoRef.current) return;
    irPara("/detalheChamado/Assinatura");
  }

  function abrirFoto(tipo: TipoFoto) {
    if (!visita) return;
    if (itensEstado.length === 0) {
      Alert.alert(
        "Nenhum equipamento",
        "Nenhum equipamento vinculado a esta OS. Contate o escritório."
      );
      return;
    }
    if (itensEstado.length === 1) {
      irParaFoto(tipo, itensEstado[0]);
      return;
    }
    setFotoPendente(tipo); // varios equipamentos: o tecnico escolhe
  }

  function irParaFoto(tipo: TipoFoto, equip: EquipamentoEstado) {
    if (!visita) return;
    setFotoPendente(null);
    router.push({
      pathname:
        tipo === "defeito"
          ? "/detalheChamado/RegistroFotoDefeito"
          : "/detalheChamado/RegistroFotoConserto",
      params: {
        chamadoId: String(idOs),
        visitaId: String(visita.id_visita),
        servicoId: String(equip.id_servico), // id_servico do estado; nunca POST .../servicos
        equipamento: `${equip.modelo} - série ${equip.numero_serie || "S/N"}`,
      },
    });
  }

  function abrirRegistro(equip: EquipamentoEstado) {
    if (!visita) return;
    router.push({
      pathname: "/detalheChamado/registroEquipamento",
      params: {
        chamadoId: String(idOs),
        visitaId: String(visita.id_visita),
        servicoId: String(equip.id_servico),
      },
    });
  }

  function abrirDespesas() {
    if (!visita) return;
    router.push(`/detalheChamado/DespesasVisita?chamadoId=${idOs}&visitaId=${visita.id_visita}`);
  }

  async function handleSubmitPausa(payload: { motivo: string; descricao?: string }) {
    if (!visita) return;
    // Erros (validacao local, sessao) sobem para o PausaModal, que os exibe junto ao formulario.
    await registrarPausa({ idOs, idVisita: visita.id_visita }, payload.motivo, payload.descricao);
    setShowPausaModal(false);
    Alert.alert(
      "OS pausada",
      "Pausa salva no aparelho e será enviada com a conexão. Finalize o deslocamento de volta."
    );
  }

  return (
    <View style={{ flex: 1 }}>
      <Header leftIconName="arrow-back" onLeftIconPress={() => router.replace("/Home/indexHome")} />

      <ScrollView style={styles.container}>
        {erro ? (
          <Text style={{ color: colors.red[900], fontSize: 13, marginTop: 8 }}>
            Não foi possível atualizar os dados: {erro}
          </Text>
        ) : null}

        {bloqueada ? (
          <View style={styles.avisoBox}>
            <Text style={styles.avisoTitulo}>Ações bloqueadas</Text>
            <Text style={styles.avisoTexto}>
              Passaram-se mais de 24 horas desde o último login com internet. Conecte-se e entre
              novamente para registrar novas ações. O que já foi salvo continua guardado.
            </Text>
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

        {/* Top */}
        <View style={styles.top}>
          <Text style={styles.osTitle}>OS #{chamado.pedido || chamado.id_os}</Text>
          <Text style={styles.status}>Status: {String(chamado.status)}</Text>

          {os.acoesPendentes > 0 ? (
            <View style={styles.avisoBox}>
              <SeloAcao status="pendente" />
              <Text style={[styles.avisoTexto, { marginTop: 6 }]}>
                {os.acoesPendentes === 1
                  ? "1 ação desta OS aguarda envio ao servidor."
                  : `${os.acoesPendentes} ações desta OS aguardam envio ao servidor.`}{" "}
                O status acima já considera essas ações.
              </Text>
            </View>
          ) : null}

          {ui.aguardandoReagendamento ? (
            <View style={styles.avisoBox}>
              <Text style={styles.avisoTitulo}>Aguardando reagendamento</Text>
              <Text style={styles.avisoTexto}>
                A visita foi encerrada com pausa
                {estado?.motivo_pausa ? ` (${estado.motivo_pausa})` : ""}. O administrador fará o
                reagendamento e uma nova visita será gerada.
              </Text>
            </View>
          ) : ui.finalizada ? (
            <View style={styles.avisoBox}>
              <Text style={styles.avisoTitulo}>OS finalizada</Text>
              <Text style={styles.avisoTexto}>Não há ações pendentes para esta OS.</Text>
            </View>
          ) : !visita ? (
            <View style={styles.avisoBox}>
              <Text style={styles.avisoTitulo}>Sem visita agendada</Text>
              <Text style={styles.avisoTexto}>
                Esta OS ainda não possui visita. Aguarde o agendamento pelo administrador.
              </Text>
            </View>
          ) : !estado ? (
            <View style={styles.avisoBox}>
              <Text style={styles.avisoTexto}>
                O estado da visita ainda não foi baixado para o aparelho. Conecte-se e sincronize.
              </Text>
              <View style={{ marginTop: 8 }}>
                <Button
                  title="Sincronizar agora"
                  onPress={sincronizarAgora}
                  loading={sincronizando}
                  width="100%"
                  fontSize={14}
                />
              </View>
            </View>
          ) : ui.acao ? (
            <View style={styles.blocoAcao}>
              <Button
                title={ui.textoAcao}
                onPress={handleAcaoPrincipal}
                loading={executando}
                width="100%"
                fontSize={15}
              />
            </View>
          ) : null}

          {visita && estado && ui.mostrarBotoesAtendimento && (
            <>
              <View style={styles.blocoAcao}>
                <Button
                  title="Iniciar atendimento"
                  onPress={handleIniciarAtendimento}
                  loading={executando}
                  disabled={!ui.podeIniciarAtendimento}
                  width="100%"
                  fontSize={15}
                />
                {!ui.podeIniciarAtendimento && ui.bloqueioIniciar ? (
                  <View style={styles.avisoBox}>
                    <Text style={styles.avisoTexto}>{ui.bloqueioIniciar}</Text>
                  </View>
                ) : null}
              </View>

              <View style={styles.blocoAcao}>
                <Button
                  title="Finalizar atendimento"
                  onPress={handleFinalizarAtendimento}
                  disabled={!ui.podeFinalizarAtendimento}
                  width="100%"
                  fontSize={15}
                />
                {!ui.podeFinalizarAtendimento && ui.bloqueioFinalizar ? (
                  <View style={styles.avisoBox}>
                    <Text style={styles.avisoTexto}>{ui.bloqueioFinalizar}</Text>
                  </View>
                ) : null}
              </View>
            </>
          )}

          {ui.pausada && (
            <View style={styles.blocoAcao}>
              <Text style={{ color: colors.red[900], fontWeight: "700" }}>
                OS pausada: {estado?.motivo_pausa ?? "motivo não informado"}. Finalize o
                deslocamento de volta para encerrar esta visita.
              </Text>
            </View>
          )}

          {ui.podePausar && (
            <View style={styles.blocoAcao}>
              <Button
                title="Pausar OS"
                variant="secondary"
                onPress={() => setShowPausaModal(true)}
                width="100%"
                fontSize={14}
              />
            </View>
          )}

          {ui.podeFotoDefeito && (
            <View style={styles.blocoAcao}>
              <Button
                title="Registrar Foto do Defeito"
                variant="secondary"
                onPress={() => abrirFoto("defeito")}
                width="100%"
                fontSize={14}
              />
            </View>
          )}

          {ui.podeRegistrarConserto && (
            <View style={styles.blocoAcao}>
              <Button
                title="Registrar Foto do Conserto"
                variant="secondary"
                onPress={() => abrirFoto("conserto")}
                width="100%"
                fontSize={14}
              />
            </View>
          )}

          {ui.visitaAberta && (
            <View style={styles.blocoAcao}>
              <Button
                title="Pedágio e frete"
                variant="secondary"
                onPress={abrirDespesas}
                width="100%"
                fontSize={14}
              />
            </View>
          )}

          <PausaModal
            visible={showPausaModal}
            onCancel={() => setShowPausaModal(false)}
            onSubmit={handleSubmitPausa}
          />

          <EquipamentoPickerModal
            visible={fotoPendente !== null}
            titulo={fotoPendente === "conserto" ? "Foto do conserto" : "Foto do defeito"}
            tipo={fotoPendente ?? "defeito"}
            equipamentos={itensEstado}
            onSelect={(e) => fotoPendente && irParaFoto(fotoPendente, e)}
            onCancel={() => setFotoPendente(null)}
          />

          <Text style={styles.descricao}>{chamado.descricao_cliente || "Sem descrição"}</Text>
        </View>

        {/* Equipamentos */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>EQUIPAMENTOS</Text>

          <View style={styles.equipList}>
            {equipamentosExibidos.length === 0 ? (
              <View style={styles.avisoBox}>
                <Text style={styles.avisoTexto}>
                  Nenhum equipamento vinculado a esta OS. Contate o escritório.
                </Text>
              </View>
            ) : (
              equipamentosExibidos.map((equip, i) => {
                const item = itensEstado[i];
                return (
                  <View
                    key={item ? item.id_servico : `os-${i}-${equip.numero_serie}`}
                    style={styles.equipCardWrapper}
                  >
                    <CardEquipamento
                      equip={equip}
                      onPress={
                        item && ui.podeRegistrarConserto ? () => abrirRegistro(item) : undefined
                      }
                      textoAcao="Registrar atendimento"
                    />
                  </View>
                );
              })
            )}
          </View>
        </View>

        {/* Cliente */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>CLIENTE</Text>

          <Text style={styles.clienteTitle}>
            {chamado.cliente_nome || cliente?.razao_social || "Cliente não informado"}
          </Text>

          <View style={styles.clientCard}>
            <Text style={styles.clientLabel}>Endereço</Text>
            {temEndereco ? (
              <>
                <Text style={styles.clientAddress}>{enderecoFormatado.linha1}</Text>
                <Text style={styles.clientAddress}>{enderecoFormatado.linha2}</Text>
                <View style={{ marginTop: 8 }}>
                  <Button
                    title="Abrir no mapa"
                    variant="secondary"
                    onPress={abrirNoMapa}
                    width="100%"
                    fontSize={14}
                  />
                </View>
              </>
            ) : (
              <Text style={styles.clientAddress}>
                {clienteErro
                  ? "Endereço indisponível sem internet. Abra esta OS uma vez com conexão para guardá-lo no aparelho."
                  : "Endereço não informado."}
              </Text>
            )}
          </View>
        </View>

        {/* Acoes desta OS: estado de envio de cada uma (RF-21) */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>AÇÕES DESTA OS</Text>
          {acoes.length === 0 ? (
            <View style={styles.avisoBox}>
              <Text style={styles.avisoTexto}>Nenhuma ação registrada neste aparelho para esta OS.</Text>
            </View>
          ) : (
            acoes.slice(0, MAX_ACOES_LISTADAS).map((ev) => (
              <View key={ev.client_event_id} style={styles.avisoBox}>
                <Text style={styles.avisoTitulo}>{ROTULO_EVENTO[ev.tipo] ?? ev.tipo}</Text>
                <Text style={styles.avisoTexto}>{formatDateTime(ev.ocorrido_em)}</Text>
                <View style={{ marginTop: 4 }}>
                  <SeloAcao status={ev.status} />
                </View>
                {ev.status === "rejeitado" ? (
                  <Text style={[styles.avisoTexto, { color: colors.red[900], marginTop: 4 }]}>
                    {MOTIVO_CODIGO[ev.codigo ?? ""] ?? "Rejeitada pelo servidor."}
                    {ev.detalhe ? `\n${ev.detalhe}` : ""}
                  </Text>
                ) : null}
              </View>
            ))
          )}
          {acoes.length > MAX_ACOES_LISTADAS || acoes.some((a) => a.status === "rejeitado") ? (
            <View style={{ marginTop: 4 }}>
              <Button
                title="Ver pendências e rejeições"
                variant="secondary"
                onPress={() => irParaPendencias(router)}
                width="100%"
                fontSize={14}
              />
            </View>
          ) : null}
        </View>

        <View style={{ height: 32 }} />
      </ScrollView>
    </View>
  );
}
