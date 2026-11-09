import React from "react";
import { useLocalSearchParams } from "expo-router";
import { FotoCapturaScreen } from "@/components/FotoCaptura/indexFotoCaptura";
import { paramNum, paramStr } from "@/utils/params";

export default function RegistroFotoDefeitoScreen() {
  const params = useLocalSearchParams<{ chamadoId?: string; visitaId?: string; servicoId?: string; equipamento?: string }>();
  return (
    <FotoCapturaScreen
      tipo="defeito"
      chamadoId={paramNum(params.chamadoId)}
      visitaId={paramNum(params.visitaId)}
      servicoId={paramNum(params.servicoId)}
      equipamento={paramStr(params.equipamento)}
    />
  );
}
