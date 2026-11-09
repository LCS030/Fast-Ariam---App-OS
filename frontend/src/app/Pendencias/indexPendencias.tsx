// Tela "Ações rejeitadas / pendências" (RF-21, SY-08, CA-36).
// Mostra, sem dados fictícios, o que ainda não foi confirmado pelo servidor e o que foi rejeitado
// (com o motivo). Nada aqui apaga eventos: "Dispensar" só oculta da lista.
import React, { useCallback, useState } from "react";
import { View, Text, ScrollView, ActivityIndicator, Alert, StyleSheet } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { Header } from "@/components/header/indexHeader";
import { Button } from "@/components/button/indexButton";
import { SeloAcao } from "@/components/SeloAcao/indexSeloAcao";
import { colors } from "@/styles/Colors";
import { styleAviso } from "@/styles/styleAviso";
import { alertError, getErrorMessage } from "@/utils/alerts";
import { formatDateTime } from "@/utils/formatDate";
import { getSessao, MSG_SESSAO } from "@/offline/sessao";
import { listarEventosPendentes, listarEventosRejeitados } from "@/offline/outbox";
import { dispensarRejeicao, reenviarEventoRejeitado } from "@/offline/acoes";
import { sincronizar } from "@/offline/sync";
import { useStatusOffline, useVersaoLocal } from "@/offline/store";
import { EventoOutbox, MOTIVO_CODIGO, ROTULO_EVENTO } from "@/offline/tipos";

/** Rejeicoes em que reenviar (com novo client_event_id) pode funcionar depois da correcao. */
const REENVIAVEIS = new Set([
  "FOTO_DEFEITO_AUSENTE",
  "CONSERTO_INCOMPLETO",
  "DEPENDENCIA_REJEITADA",
  "OS_PAUSADA",
  "TRANSICAO_INVALIDA",
]);

function dataEvento(ev: EventoOutbox): string {
  return formatDateTime(ev.ocorrido_em);
}

export default function PendenciasScreen() {
  const router = useRouter();
  const status = useStatusOffline();
  const versao = useVersaoLocal();

  const [pendentes, setPendentes] = useState<EventoOutbox[] | null>(null);
  const [rejeitadas, setRejeitadas] = useState<EventoOutbox[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [sincronizando, setSincronizando] = useState(false);
  const [resultado, setResultado] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null); // client_event_id em tratamento

  const carregar = useCallback(async () => {
    try {
      const sessao = await getSessao();
      if (!sessao) {
        setPendentes([]);
        setRejeitadas([]);
        setErro(null);
        return;
      }
      const [p, r] = await Promise.all([
        listarEventosPendentes(sessao.idTecnico),
        listarEventosRejeitados(sessao.idTecnico),
      ]);
      setPendentes(p);
      setRejeitadas(r);
      setErro(null);
    } catch (err) {
      setErro(getErrorMessage(err, "Falha ao ler as ações salvas no aparelho."));
    }
    // `versao` refaz a leitura quando a fila muda.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versao]);

  useFocusEffect(
    useCallback(() => {
      carregar();
    }, [carregar])
  );

  async function sincronizarAgora() {
    if (sincronizando) return;
    setSincronizando(true);
    setResultado(null);
    try {
      const r = await sincronizar();
      setResultado(
        r.ok
          ? "Sincronizado. Tudo o que estava pendente foi processado."
          : r.motivo === "offline"
          ? "Sem conexão com a internet. As ações continuam guardadas no aparelho."
          : r.mensagem ?? "Não foi possível sincronizar agora. As ações continuam guardadas."
      );
    } finally {
      setSincronizando(false);
      await carregar();
    }
  }

  function reenviar(ev: EventoOutbox) {
    Alert.alert(
      "Reenviar ação",
      "A ação será enviada de novo, com um novo identificador e o horário de agora. Corrija antes o que faltou (por exemplo, tire a foto) para que ela seja aceita.",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Reenviar",
          onPress: async () => {
            setOcupado(ev.client_event_id);
            try {
              await reenviarEventoRejeitado(ev.client_event_id);
            } catch (err) {
              alertError(err, "Não foi possível reenviar a ação.");
            } finally {
              setOcupado(null);
            }
          },
        },
      ]
    );
  }

  function dispensar(ev: EventoOutbox) {
    Alert.alert(
      "Dispensar aviso",
      "A ação continua registrada no aparelho (nada é apagado), mas deixa de aparecer nesta lista.",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Dispensar",
          style: "destructive",
          onPress: async () => {
            setOcupado(ev.client_event_id);
            try {
              await dispensarRejeicao(ev.client_event_id);
            } catch (err) {
              alertError(err, "Não foi possível dispensar o aviso.");
            } finally {
              setOcupado(null);
            }
          },
        },
      ]
    );
  }

  function abrirOs(ev: EventoOutbox) {
    router.push({ pathname: "/detalheChamado/[id]", params: { id: String(ev.id_os) } });
  }

  function voltar() {
    if (router.canGoBack()) router.back();
    else router.replace("/Home/indexHome");
  }

  const exigeLogin =
    status.situacaoSessao === "jwt_expirado" || status.situacaoSessao === "offline_expirada";

  return (
    <View style={{ flex: 1, backgroundColor: "#fff" }}>
      <Header leftIconName="arrow-back" onLeftIconPress={voltar} />

      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 32 }}>
        <Text style={s.titulo}>Pendências de envio</Text>

        {/* Resumo */}
        <View style={styleAviso.box}>
          <Text style={styleAviso.texto}>
            Conexão: {status.online ? "online" : "sem internet"}
            {status.sincronizando ? " (sincronizando...)" : ""}
          </Text>
          <Text style={styleAviso.texto}>
            Ações aguardando envio: {status.pendentes} · Fotos/assinaturas aguardando: {status.arquivosPendentes}
          </Text>
          <Text style={styleAviso.texto}>
            Última sincronização:{" "}
            {status.ultimoSync ? formatDateTime(new Date(status.ultimoSync).toISOString()) : "ainda não houve"}
          </Text>
        </View>

        {exigeLogin ? (
          <View style={styleAviso.boxErro}>
            <Text style={styleAviso.titulo}>
              {status.situacaoSessao === "offline_expirada" ? "Sessão offline encerrada" : "Sessão expirada"}
            </Text>
            <Text style={styleAviso.texto}>{MSG_SESSAO[status.situacaoSessao]}</Text>
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

        <Button
          title="Sincronizar agora"
          onPress={sincronizarAgora}
          loading={sincronizando}
          disabled={exigeLogin}
          width="100%"
          fontSize={15}
        />
        {resultado ? <Text style={[styleAviso.texto, { marginTop: 8 }]}>{resultado}</Text> : null}
        {status.erroSync && status.online && !resultado ? (
          <Text style={[styleAviso.texto, { marginTop: 8, color: colors.red[900] }]}>
            Último envio falhou: {status.erroSync}
          </Text>
        ) : null}

        {pendentes === null && !erro ? (
          <View style={{ marginTop: 24 }}>
            <ActivityIndicator size="large" />
          </View>
        ) : erro ? (
          <View style={[styleAviso.boxErro, { marginTop: 16 }]}>
            <Text style={styleAviso.texto}>{erro}</Text>
            <View style={{ marginTop: 8 }}>
              <Button title="Tentar novamente" onPress={carregar} width="100%" fontSize={14} />
            </View>
          </View>
        ) : (
          <>
            {/* Rejeitadas */}
            <Text style={s.secao}>AÇÕES REJEITADAS</Text>
            {rejeitadas.length === 0 ? (
              <Text style={s.vazio}>Nenhuma ação rejeitada.</Text>
            ) : (
              rejeitadas.map((ev) => (
                <View key={ev.client_event_id} style={s.card}>
                  <Text style={s.cardTitulo}>{ROTULO_EVENTO[ev.tipo] ?? ev.tipo}</Text>
                  <Text style={s.cardSub}>{ev.rotulo_os ?? `OS #${ev.id_os}`}</Text>
                  <Text style={s.cardSub}>Registrada em {dataEvento(ev)}</Text>
                  <View style={{ marginVertical: 6 }}>
                    <SeloAcao status="rejeitado" />
                  </View>
                  <Text style={s.motivo}>
                    {MOTIVO_CODIGO[ev.codigo ?? ""] ?? "A ação foi rejeitada."}
                  </Text>
                  {ev.detalhe ? <Text style={s.detalhe}>{ev.detalhe}</Text> : null}
                  {ev.codigo === "FOTO_DEFEITO_AUSENTE" || ev.codigo === "CONSERTO_INCOMPLETO" ? (
                    <Text style={s.detalhe}>
                      Abra a OS, registre o que falta (foto/conserto) e depois reenvie esta ação.
                    </Text>
                  ) : null}
                  <View style={s.botoes}>
                    <Button
                      title="Abrir OS"
                      variant="secondary"
                      onPress={() => abrirOs(ev)}
                      disabled={ocupado === ev.client_event_id}
                      fontSize={14}
                    />
                    {REENVIAVEIS.has(ev.codigo ?? "") ? (
                      <Button
                        title="Reenviar"
                        onPress={() => reenviar(ev)}
                        loading={ocupado === ev.client_event_id}
                        disabled={exigeLogin}
                        fontSize={14}
                      />
                    ) : null}
                    <Button
                      title="Dispensar"
                      variant="secondary"
                      onPress={() => dispensar(ev)}
                      disabled={ocupado === ev.client_event_id}
                      fontSize={14}
                    />
                  </View>
                </View>
              ))
            )}

            {/* Pendentes */}
            <Text style={s.secao}>AGUARDANDO ENVIO</Text>
            {pendentes && pendentes.length === 0 ? (
              <Text style={s.vazio}>Nenhuma ação aguardando envio.</Text>
            ) : (
              pendentes?.map((ev) => (
                <View key={ev.client_event_id} style={s.card}>
                  <Text style={s.cardTitulo}>{ROTULO_EVENTO[ev.tipo] ?? ev.tipo}</Text>
                  <Text style={s.cardSub}>{ev.rotulo_os ?? `OS #${ev.id_os}`}</Text>
                  <Text style={s.cardSub}>Registrada em {dataEvento(ev)}</Text>
                  <View style={{ marginTop: 6 }}>
                    <SeloAcao status="pendente" />
                  </View>
                  {ev.codigo === "ARQUIVO_AUSENTE" ? (
                    <Text style={s.detalhe}>Aguardando o envio da foto/assinatura desta ação.</Text>
                  ) : null}
                  {ev.tentativas > 0 ? (
                    <Text style={s.detalhe}>
                      {ev.tentativas === 1 ? "1 tentativa de envio" : `${ev.tentativas} tentativas de envio`}
                    </Text>
                  ) : null}
                </View>
              ))
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  titulo: { fontSize: 22, fontWeight: "700", color: colors.blue[900], marginBottom: 8 },
  secao: {
    marginTop: 20,
    marginBottom: 8,
    paddingVertical: 8,
    paddingHorizontal: 10,
    backgroundColor: colors.blue[900],
    color: "#fff",
    fontWeight: "700",
    fontSize: 14,
  },
  vazio: { color: colors.gray[500], fontSize: 14, marginBottom: 8 },
  card: {
    padding: 12,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: colors.gray[200],
    borderRadius: 10,
    backgroundColor: "#fff",
  },
  cardTitulo: { fontSize: 15, fontWeight: "700", color: colors.blue[900] },
  cardSub: { fontSize: 13, color: colors.gray[500] },
  motivo: { fontSize: 14, color: colors.gray[800], fontWeight: "700" },
  detalhe: { fontSize: 13, color: colors.gray[800], marginTop: 2 },
  botoes: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
});
