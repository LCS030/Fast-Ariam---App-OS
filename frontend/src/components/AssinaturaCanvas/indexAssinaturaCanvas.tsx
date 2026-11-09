/****************************************************************************************
 * FILE: src/components/AssinaturaCanvas/indexAssinaturaCanvas.tsx
 ****************************************************************************************/
import React, { useRef } from "react";
import { View, Text, TouchableOpacity, Alert } from "react-native";
import { WebView } from "react-native-webview";
import { styles } from "../../styles/styleAssinaturaCanvas";
import { colors } from "@/styles/Colors";

interface Props {
  /** Chamado com a imagem PNG (data URI) quando o tecnico confirma a assinatura. */
  onOK: (base64: string) => void;
  /** Chamado ao limpar o quadro (a assinatura anterior deixa de valer). */
  onClear?: () => void;
}

export function AssinaturaCanvas({ onOK, onClear }: Props) {
  const webRef = useRef<WebView>(null);

  const html = `
    <html>
      <head><meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no" /></head>
      <body style="margin:0; padding:0; overflow:hidden;">
        <canvas id="canvas"
          style="touch-action:none; background:#fff; width:100vw; height:100vh;">
        </canvas>

        <script>
          const canvas = document.getElementById("canvas");
          const ctx = canvas.getContext("2d");
          let drawing = false;
          let hasInk = false;
          let saved = false;

          function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            hasInk = false;
          }

          resize();
          window.addEventListener("resize", resize);

          function pos(e) {
            const x = e.touches ? e.touches[0].clientX : e.clientX;
            const y = e.touches ? e.touches[0].clientY : e.clientY;
            return { x, y };
          }

          function start(e) {
            e.preventDefault();
            if (saved) {
              // novo traco depois de salvar: a assinatura salva deixa de valer ate salvar de novo
              saved = false;
              window.ReactNativeWebView.postMessage(JSON.stringify({ type: "clear" }));
            }
            drawing = true;
            const { x, y } = pos(e);
            ctx.beginPath();
            ctx.moveTo(x, y);
          }

          function end() {
            drawing = false;
            ctx.beginPath();
          }

          function draw(e) {
            if (!drawing) return;
            e.preventDefault();
            const { x, y } = pos(e);
            ctx.lineWidth = 3;
            ctx.lineCap = "round";
            ctx.strokeStyle = "${colors.blue[900]}";
            ctx.lineTo(x, y);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(x, y);
            hasInk = true;
          }

          // Mouse
          canvas.addEventListener("mousedown", start);
          canvas.addEventListener("mouseup", end);
          canvas.addEventListener("mousemove", draw);

          // Touch (passive:false para poder impedir o scroll da tela enquanto assina)
          canvas.addEventListener("touchstart", start, { passive: false });
          canvas.addEventListener("touchend", end);
          canvas.addEventListener("touchmove", draw, { passive: false });

          function saveSignature() {
            if (!hasInk) {
              window.ReactNativeWebView.postMessage(JSON.stringify({ type: "empty" }));
              return;
            }
            window.ReactNativeWebView.postMessage(JSON.stringify({
              type: "save",
              data: canvas.toDataURL("image/png")
            }));
            saved = true;
          }

          function clearSignature() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            hasInk = false;
            saved = false;
            window.ReactNativeWebView.postMessage(JSON.stringify({ type: "clear" }));
          }

          function handleMessage(event) {
            const msg = event.data;
            if (msg === "save") saveSignature();
            if (msg === "clear") clearSignature();
          }

          // Android
          document.addEventListener("message", handleMessage);
          // iOS
          window.addEventListener("message", handleMessage);
        </script>
      </body>
    </html>
  `;

  return (
    <View style={styles.container}>
      <Text style={styles.label}>Assinatura do Cliente</Text>

      <View style={styles.box}>
        <WebView
          ref={webRef}
          originWhitelist={["*"]}
          javaScriptEnabled
          nestedScrollEnabled
          source={{ html }}
          onMessage={(event) => {
            let msg: { type?: string; data?: string };
            try {
              msg = JSON.parse(event.nativeEvent.data);
            } catch {
              return;
            }

            if (msg.type === "save" && msg.data) {
              onOK(msg.data);
              Alert.alert("Assinatura salva", "A assinatura foi registrada.");
            } else if (msg.type === "empty") {
              Alert.alert("Assinatura vazia", "Peça ao cliente para assinar antes de salvar.");
            } else if (msg.type === "clear") {
              onClear?.();
            }
          }}
        />
      </View>

      <TouchableOpacity
        style={styles.btnClear}
        onPress={() => webRef.current?.postMessage("clear")}
      >
        <Text style={styles.btnClearText}>Limpar</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.btnSave}
        onPress={() => webRef.current?.postMessage("save")}
      >
        <Text style={styles.btnSaveText}>Salvar Assinatura</Text>
      </TouchableOpacity>
    </View>
  );
}
