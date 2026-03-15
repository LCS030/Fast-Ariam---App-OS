import React, { useState } from "react";
import { View, Text, KeyboardAvoidingView, Platform } from "react-native";
import { useRouter } from "expo-router";
import { Input } from "@/components/input/indexInput";
import { Button } from "@/components/button/indexButton";
import { Header } from "@/components/header/indexHeader";
import  api from "@/api/api"
import { setToken, getToken } from "@/utils/storage";
import { alertError } from "@/utils/alerts";
import { styles } from "@/styles/styleLogin";
import { loginTecnico } from "@/api/tecnico";


export default function LoginScreen() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
  if (!email || !senha) {
    alertError(null, "Preencha email e senha.");
    return;
  }

  try {
    setLoading(true);

    const form = new FormData();
    form.append("username", email.toLowerCase());
    form.append("password", senha);

    const res = await api.post("auth/login", form, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    })

    await setToken(res.data.access_token);
    
    console.log("TOKEN SALVO:", await getToken());

    router.replace("/Home/indexHome");

  } catch (err) {
    alertError(err);
  } finally {
    setLoading(false);
  }
}

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1 }}
    >
      <Header leftIconName={null} />

      <View style={styles.container}>
        <Text style={styles.title}>Acessar Conta</Text>

        <Input
          label="Email"
          value={email}
          onChangeText={setEmail}
          placeholder="exemplo@fast.com"
        />

        <Input
          label="Senha"
          value={senha}
          onChangeText={setSenha}
          secure
          placeholder="••••••••"
        />

        <Button title="Entrar" onPress={handleLogin} loading={loading} />
      </View>
    </KeyboardAvoidingView>
  );
}
