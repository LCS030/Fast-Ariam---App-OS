import React, { useEffect, useState } from "react";
import { View, Text, KeyboardAvoidingView, Platform, ScrollView, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Input } from "@/components/input/indexInput";
import { Button } from "@/components/button/indexButton";
import { Header } from "@/components/header/indexHeader";
import { setToken, removeToken } from "@/utils/storage";
import { resetSessionExpired } from "@/utils/session";
import { alertError } from "@/utils/alerts";
import { styles } from "@/styles/styleLogin";
import { colors } from "@/styles/Colors";
import { loginTecnico, getPerfilTecnico } from "@/api/tecnico";
import {
  avaliarSessao,
  encerrarSessao,
  iniciarSessaoOnline,
  MSG_SESSAO,
  SituacaoSessao,
} from "@/offline/sessao";
import { contarFila } from "@/offline/outbox";
import { atualizarContagens } from "@/offline/status";
import { dispararSync } from "@/offline/sync";

export default function LoginScreen() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [loading, setLoading] = useState(false);
  // Sessao que ja existe no aparelho: explica por que o login e pedido e permite voltar offline.
  const [situacao, setSituacao] = useState<SituacaoSessao>("sem_sessao");
  const [guardadas, setGuardadas] = useState(0);

  useEffect(() => {
    let ativo = true;
    (async () => {
      const a = await avaliarSessao();
      const n = a.sessao ? (await contarFila(a.sessao.idTecnico)).pendentes : 0;
      if (ativo) {
        setSituacao(a.situacao);
        setGuardadas(n);
      }
    })().catch(() => undefined);
    return () => {
      ativo = false;
    };
  }, []);

  async function handleLogin() {
    if (loading) return;

    if (!email.trim() || !senha) {
      alertError(null, "Preencha email e senha.");
      return;
    }

    let tokenNovoGravado = false;
    try {
      setLoading(true);

      // O primeiro login (e o de renovacao) exige internet. Falha de rede NAO apaga a sessao
      // anterior: o tecnico ainda pode voltar a operar offline dentro das 24 h.
      const { access_token } = await loginTecnico(email, senha);
      await setToken(access_token);
      tokenNovoGravado = true;
      resetSessionExpired();

      // PR-06: confirma o perfil em GET /api/auth/me ({id_tecnico, nome, email, role, is_active}).
      // Este app e do tecnico: outros papeis ou contas inativas nao entram.
      const perfil = await getPerfilTecnico();
      if (!perfil.is_active) {
        await removeToken();
        await encerrarSessao();
        alertError(null, "Usuário inativo. Procure o administrador.");
        return;
      }
      if (perfil.role !== "tecnico") {
        await removeToken();
        await encerrarSessao();
        alertError(null, "Este aplicativo é exclusivo para técnicos.");
        return;
      }

      // Instante do ultimo login ONLINE: base da janela de 24 h offline (RN-39).
      await iniciarSessaoOnline({ id_tecnico: perfil.id_tecnico, nome: perfil.nome });
      await atualizarContagens();
      dispararSync(); // envia o que ficou guardado e atualiza as OS

      router.replace("/Home/indexHome");
    } catch (err) {
      if (tokenNovoGravado) {
        await removeToken();
        await encerrarSessao();
      }
      alertError(err, "Não foi possível entrar. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  const podeContinuarOffline = situacao === "ok" || situacao === "jwt_expirado";

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1 }}
    >
      <Header leftIconName={null} />

      <ScrollView
        contentContainerStyle={{ flexGrow: 1 }}
        keyboardShouldPersistTaps="handled"
        style={{ backgroundColor: styles.container.backgroundColor }}
      >
        <View style={styles.container}>
          <Text style={styles.title}>Acessar Conta</Text>

          {situacao === "offline_expirada" || situacao === "jwt_expirado" ? (
            <View style={local.aviso}>
              <Text style={local.avisoTitulo}>
                {situacao === "offline_expirada" ? "Sessão offline encerrada" : "Sessão expirada"}
              </Text>
              <Text style={local.avisoTexto}>{MSG_SESSAO[situacao]}</Text>
              {guardadas > 0 ? (
                <Text style={local.avisoTexto}>
                  {guardadas === 1
                    ? "1 ação aguardando envio."
                    : `${guardadas} ações aguardando envio.`}{" "}
                  Entre com a mesma conta para enviá-las.
                </Text>
              ) : null}
            </View>
          ) : null}

          <Input
            label="Email"
            value={email}
            onChangeText={setEmail}
            placeholder="exemplo@fast.com"
            keyboardType="email-address"
            autoCapitalize="none"
            editable={!loading}
          />

          <Input
            label="Senha"
            value={senha}
            onChangeText={setSenha}
            secure
            placeholder="••••••••"
            autoCapitalize="none"
            editable={!loading}
          />

          <Button title="Entrar" onPress={handleLogin} loading={loading} />

          {podeContinuarOffline ? (
            <View style={{ marginTop: 12 }}>
              <Button
                title="Continuar sem conexão"
                variant="secondary"
                onPress={() => router.replace("/Home/indexHome")}
                disabled={loading}
              />
            </View>
          ) : null}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const local = StyleSheet.create({
  aviso: {
    marginBottom: 16,
    padding: 12,
    backgroundColor: "#fff",
    borderRadius: 8,
    borderLeftWidth: 4,
    borderLeftColor: colors.blue[900],
    gap: 4,
  },
  avisoTitulo: { color: colors.blue[900], fontSize: 16, fontWeight: "700" },
  avisoTexto: { color: colors.gray[800], fontSize: 14 },
});
