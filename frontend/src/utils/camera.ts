// Captura e validacao local de imagens (RN-21, RN-37, CA-14, CA-15).
// A validacao e conveniencia: API e bucket revalidam.
import { Alert, Image } from "react-native";
import * as ImagePicker from "expo-image-picker";
import type { ArquivoImagem } from "@/api/arquivo";

export const MAX_IMAGE_BYTES = 15 * 1024 * 1024; // 15 MB por imagem
// Minimo equivalente a 960x1280 em QUALQUER orientacao (retrato ou paisagem):
// menor lado >= 960 e maior lado >= 1280 (decisao do PO; o backend aceita igual).
export const CONSERTO_MIN_LADO_MENOR = 960;
export const CONSERTO_MIN_LADO_MAIOR = 1280;

export function resolucaoConsertoValida(width: number, height: number): boolean {
  return (
    Math.min(width, height) >= CONSERTO_MIN_LADO_MENOR &&
    Math.max(width, height) >= CONSERTO_MIN_LADO_MAIOR
  );
}

/** conserto: exige resolucao minima. Demais (defeito, odometro, deslocamento, comprovante): sem minimo. */
export type TipoFoto = "conserto" | "outra";

export interface FotoCapturada extends ArquivoImagem {
  width: number;
  height: number;
  bytes: number | null;
}

function detectarMime(asset: ImagePicker.ImagePickerAsset): "image/jpeg" | "image/png" | null {
  const mime = (asset.mimeType ?? "").toLowerCase();
  if (mime === "image/jpeg" || mime === "image/jpg") return "image/jpeg";
  if (mime === "image/png") return "image/png";
  if (mime) return null; // outro tipo informado (webp, heic...) nao e aceito

  // sem mimeType: usa a extensao; camera do Android entrega JPEG
  const caminho = (asset.fileName ?? asset.uri).split("?")[0].toLowerCase();
  if (caminho.endsWith(".png")) return "image/png";
  if (caminho.endsWith(".jpg") || caminho.endsWith(".jpeg")) return "image/jpeg";
  return null;
}

async function tamanhoEmBytes(asset: ImagePicker.ImagePickerAsset): Promise<number | null> {
  if (typeof asset.fileSize === "number" && asset.fileSize > 0) return asset.fileSize;
  try {
    const resp = await fetch(asset.uri);
    const blob = await resp.blob();
    return blob.size;
  } catch {
    return null; // nao foi possivel medir: o servidor valida de novo
  }
}

function dimensoesDoArquivo(uri: string): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    Image.getSize(
      uri,
      (width, height) => resolve({ width, height }),
      () => resolve(null)
    );
  });
}

type Resultado = { ok: true; foto: FotoCapturada } | { ok: false; titulo: string; mensagem: string };

export async function validarFoto(
  asset: ImagePicker.ImagePickerAsset,
  tipo: TipoFoto
): Promise<Resultado> {
  const mime = detectarMime(asset);
  if (!mime) {
    return {
      ok: false,
      titulo: "Formato não aceito",
      mensagem: "Somente imagens JPEG ou PNG são aceitas.",
    };
  }

  const bytes = await tamanhoEmBytes(asset);
  if (bytes !== null && bytes > MAX_IMAGE_BYTES) {
    const mb = (bytes / (1024 * 1024)).toFixed(1).replace(".", ",");
    return {
      ok: false,
      titulo: "Imagem muito grande",
      mensagem: `A imagem tem ${mb} MB e o limite é de 15 MB. Tire a foto novamente.`,
    };
  }

  let width = asset.width;
  let height = asset.height;
  if (tipo === "conserto" && (!width || !height)) {
    const dims = await dimensoesDoArquivo(asset.uri);
    if (!dims) {
      return {
        ok: false,
        titulo: "Não foi possível validar a foto",
        mensagem: "Não foi possível ler as dimensões da imagem. Tire a foto novamente.",
      };
    }
    width = dims.width;
    height = dims.height;
  }

  if (tipo === "conserto" && !resolucaoConsertoValida(width, height)) {
    return {
      ok: false,
      titulo: "Resolução insuficiente",
      mensagem:
        `A foto do conserto precisa ter no mínimo ${CONSERTO_MIN_LADO_MENOR}x${CONSERTO_MIN_LADO_MAIOR} px ` +
        `(em retrato ou paisagem).\nSua foto: ${width}x${height} px.`,
    };
  }

  return { ok: true, foto: { uri: asset.uri, mime, width, height, bytes } };
}

/**
 * Abre a camera, valida a foto e devolve null se o tecnico cancelou ou a foto foi recusada
 * (nesse caso o motivo ja foi exibido). A compressao usa apenas qualidade JPEG: a imagem
 * NUNCA e redimensionada nem recortada, para nao perder a resolucao exigida (RN-21).
 */
export async function capturarFoto(tipo: TipoFoto): Promise<FotoCapturada | null> {
  const perm = await ImagePicker.requestCameraPermissionsAsync();
  if (!perm.granted) {
    Alert.alert("Permissão necessária", "Permita o acesso à câmera para registrar fotos.");
    return null;
  }

  const result = await ImagePicker.launchCameraAsync({
    mediaTypes: ["images"],
    quality: 0.8,
    allowsEditing: false,
  });

  if (result.canceled || !result.assets?.length) return null;

  const validacao = await validarFoto(result.assets[0], tipo);
  if (!validacao.ok) {
    Alert.alert(validacao.titulo, validacao.mensagem);
    return null;
  }
  return validacao.foto;
}
