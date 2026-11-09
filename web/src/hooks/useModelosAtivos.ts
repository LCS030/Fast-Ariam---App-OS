import { useCallback, useEffect, useRef, useState } from 'react';
import { EquipamentoModelo } from '../types';
import { ChamadoService } from '../services/chamadoService';
import { mensagemErro } from '../utils/os';

/**
 * Carrega os modelos ATIVOS do catálogo (GET /api/equipamentos/?is_active=true) quando `habilitado`.
 * Em falha expõe `erro` e lista vazia (nunca modelos fictícios — CA-05); `recarregar` alimenta o "Tentar novamente".
 */
export function useModelosAtivos(habilitado: boolean) {
  const [modelos, setModelos] = useState<EquipamentoModelo[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carregado, setCarregado] = useState(false);
  const cargaAtual = useRef(0);

  const recarregar = useCallback(async () => {
    const id = ++cargaAtual.current;
    setCarregando(true);
    setErro(null);
    try {
      const lista = await ChamadoService.listarModelos(true);
      if (id !== cargaAtual.current) return;
      setModelos(Array.isArray(lista) ? lista.filter((m) => m.is_active !== false) : []);
      setCarregado(true);
    } catch (e) {
      if (id !== cargaAtual.current) return;
      setModelos([]);
      setCarregado(false);
      setErro(mensagemErro(e, 'Não foi possível carregar o catálogo de modelos.'));
    } finally {
      if (id === cargaAtual.current) setCarregando(false);
    }
  }, []);

  useEffect(() => {
    if (habilitado) recarregar();
    else cargaAtual.current++; // descarta resposta em andamento
  }, [habilitado, recarregar]);

  return { modelos, carregando, erro, carregado, recarregar };
}
