/****************************************************************************************
 * FILE: src/components/assinaturaCanvas/indexAssinaturaCanvas.tsx
 ****************************************************************************************/
import React, { useRef } from "react";
import { View, Text, TouchableOpacity, Alert } from "react-native";
import { WebView } from "react-native-webview";
import { styles, webStyle } from "../../styles/styleAssinaturaCanvas";
import { colors } from "@/styles/Colors";

interface Props {
  onOK: (base64: string) => void;
  onClear?: () => void;
}

export function AssinaturaCanvas({ onOK, onClear }: Props) {
  const webRef = useRef<WebView>(null);

  const html = `
    <html>
      <body style="margin:0; padding:0; overflow:hidden;">
        <canvas id="canvas" 
          style="touch-action:none; background:#fff; width:100vw; height:100vh;">
        </canvas>

        <script>
          const canvas = document.getElementById("canvas");
          const ctx = canvas.getContext("2d");
          let drawing = false;

          function resize() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
          }

          resize();
          window.addEventListener("resize", resize);

          function pos(e) {
            const x = e.touches ? e.touches[0].clientX : e.clientX;
            const y = e.touches ? e.touches[0].clientY : e.clientY;
            return { x, y };
          }

          function start(e) {
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
            const { x, y } = pos(e);
            ctx.lineWidth = 3;
            ctx.lineCap = "round";
            ctx.strokeStyle = "${colors.blue[900]}";
            ctx.lineTo(x, y);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(x, y);
          }

          // Mouse
          canvas.addEventListener("mousedown", start);
          canvas.addEventListener("mouseup", end);
          canvas.addEventListener("mousemove", draw);

          // Touch
          canvas.addEventListener("touchstart", start);
          canvas.addEventListener("touchend", end);
          canvas.addEventListener("touchmove", draw);

          function saveSignature() {
            window.ReactNativeWebView.postMessage(JSON.stringify({
              type: "save",
              data: canvas.toDataURL("image/png")
            }));
          }

          function clearSignature() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
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
          source={{ html }}
          onMessage={(event) => {
            const msg = JSON.parse(event.nativeEvent.data);

            if (msg.type === "save") onOK(msg.data)
              Alert.alert("Sucesso", "Assinatura salva!")
            if (msg.type === "clear" && onClear) onClear();
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
