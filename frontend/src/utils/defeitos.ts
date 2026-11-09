// Opcoes de defeito e conversao para os valores aceitos pela API (enums da SDD 6.7.1).
// Cada opcao tem uma chave (usada na tela) e o valor enviado ao servidor.

export type Option = { key: string; label: string; value: string };

const mesmaChave = (valores: string[]): Option[] =>
  valores.map((v) => ({ key: v, label: v, value: v }));

export const OPTIONS_COMPRESSOR: Option[] = mesmaChave([
  "Queimado",
  "Em Massa",
  "Em Curto",
  "Corrente Alta",
  "Não Parte",
  "Sem Compressão",
  "Travado",
  "Com Barulho",
  "Não Succiona",
  "Desarmado",
]);

// O servidor so conhece "Nº Ponto" e "Não Localizado". O numero do ponto escolhido
// viaja no texto de vazamento_ponto_descricao (ver comporPontoDescricao).
const PONTOS: { n: string; label: string }[] = [
  { n: "1", label: "1 - Solda - Prata 30% (Aço / Aço)" },
  { n: "2", label: "2 - Solda - Prata 30% (Cobre / Aço)" },
  { n: "3", label: "3 - Tampão Lokring (Cobre)" },
  { n: "4", label: "4 - Solda - Prata 30% (Aço / Cobre)" },
  { n: "5", label: "5 - União Lokring (Cobre / Alumínio)" },
  { n: "6", label: "6 - União Lokring (Alumínio / Cobre)" },
  { n: "7", label: "7 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { n: "8", label: "8 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { n: "9", label: "9 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { n: "10", label: "10 - Solda - Prata 30% (Cobre / Aço)" },
  { n: "11", label: "11 - Solda - Prata 30% (Cobre / Aço)" },
  { n: "12", label: "12 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { n: "13", label: "13 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { n: "14", label: "14 - Solda - Prata 30% (Cobre / Aço)" },
  { n: "15", label: "15 - Solda - Prata 30% (Cobre / Aço)" },
  { n: "16", label: "16 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
  { n: "17", label: "17 - Solda - Silfoscoper 15% (Cobre / Cobre)" },
];

export const CHAVE_NAO_LOCALIZADO = "nao_localizado";

export const OPTIONS_VAZAMENTO: Option[] = [
  ...PONTOS.map((p) => ({ key: p.n, label: p.label, value: "Nº Ponto" })),
  { key: CHAVE_NAO_LOCALIZADO, label: "Não localizado", value: "Não Localizado" },
];

export const OPTIONS_OUTROS: Option[] = mesmaChave([
  "Filtro Entupido",
  "Capilar Obstruído",
  "Micromotor Queimado",
  "Micromotor Travado",
  "Controlador Queimado",
  "Regulagem Parâmetros",
]);

export const OPTIONS_ILUMINACAO: Option[] = mesmaChave([
  "Lâmpada Queimada",
  "Sem Alimentação",
  "Em Curto",
]);

export const OPTIONS_ESTRUTURA: Option[] = mesmaChave([
  "01 - Perfil Curvo Vidro",
  "02 - Perfil Suporte Iluminação",
  "03 - Lente Calha Iluminação",
  "04 - Perfil Vedação",
  "05 - Perfil Porta Etiqueta",
  "06 - Puxador",
  "07 - Porta Parachoque",
  "08 - Canto 90°",
  "09 - Acrílico Carel",
  "10 - Perfil Frontal",
  "11 - Parachoque Frontal",
  "12 - Parachoque Lateral",
]);

/** Chaves selecionadas -> valores unicos aceitos pela API. */
export function valoresDeChaves(options: Option[], chaves: string[]): string[] {
  const valores = options.filter((o) => chaves.includes(o.key)).map((o) => o.value);
  return Array.from(new Set(valores));
}

/** Valores vindos da API -> chaves da tela (opcoes de valor unico). */
export function chavesDeValores(options: Option[], valores: string[] | undefined | null): string[] {
  if (!valores) return [];
  return options.filter((o) => valores.includes(o.value)).map((o) => o.key);
}

const PREFIXO_PONTOS = "Pontos de solda selecionados: ";
const REGEX_PONTOS = /^Pontos de solda selecionados: ([\d, ]+)\.(?:\n|$)/;

/** Texto enviado em vazamento_ponto_descricao: pontos escolhidos + observacao livre. */
export function comporPontoDescricao(chaves: string[], observacao: string): string | null {
  const numeros = chaves
    .filter((k) => /^\d+$/.test(k))
    .sort((a, b) => Number(a) - Number(b));
  const texto = observacao.trim();
  const partes: string[] = [];
  if (numeros.length) partes.push(`${PREFIXO_PONTOS}${numeros.join(", ")}.`);
  if (texto) partes.push(texto);
  return partes.length ? partes.join("\n") : null;
}

/** Inverso de comporPontoDescricao: devolve os pontos marcados e a observacao livre. */
export function separarPontoDescricao(descricao: string | null | undefined): {
  chaves: string[];
  observacao: string;
} {
  const texto = descricao ?? "";
  const m = REGEX_PONTOS.exec(texto);
  if (!m) return { chaves: [], observacao: texto };
  const chaves = m[1]
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return { chaves, observacao: texto.slice(m[0].length) };
}
