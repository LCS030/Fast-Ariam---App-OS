import React, { useState } from 'react';
import { EquipamentoModelo } from '../types';
import { ApiError } from '../services/apiClient';
import { Package, Loader2 } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';

interface Props {
  /** Modelo em edição (renomear); ausente = novo modelo. O componente é montado só enquanto o modal está aberto. */
  modeloEdicao?: EquipamentoModelo | null;
  onClose: () => void;
  onSave: (nome: string) => Promise<void>;
}

const NOME_MAX = 100;

export const ModalModeloEquipamento: React.FC<Props> = ({ modeloEdicao, onClose, onSave }) => {
  const [nome, setNome] = useState(modeloEdicao?.modelo || '');
  // Erro ligado ao campo: validação local e 409 de nome duplicado (sem diferenciar maiúsculas).
  const [erroCampo, setErroCampo] = useState<string | null>(null);
  const { enviando, erro, executar } = useAcaoAssincrona();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const valor = nome.trim();
    if (valor.length < 1) {
      setErroCampo('Informe o nome do modelo.');
      return;
    }
    if (valor.length > NOME_MAX) {
      setErroCampo(`O nome do modelo aceita no máximo ${NOME_MAX} caracteres.`);
      return;
    }
    setErroCampo(null);

    let conflito = false;
    const ok = await executar(async () => {
      try {
        await onSave(valor);
      } catch (err) {
        if (err instanceof ApiError && (err.status === 409 || err.status === 422)) {
          conflito = true;
          setErroCampo(err.detail || 'Já existe um modelo com este nome.');
          return;
        }
        throw err;
      }
    });
    if (ok && !conflito) onClose();
  };

  return (
    <ModalShell
      titulo={modeloEdicao ? 'Editar modelo de equipamento' : 'Novo modelo de equipamento'}
      subtitulo="O catálogo guarda apenas o nome do modelo"
      icone={<Package className="w-5 h-5" />}
      onClose={onClose}
      erro={erro}
      larguraMax="max-w-md"
    >
      <form onSubmit={handleSubmit} className="space-y-4 text-xs" noValidate>
        <div>
          <label htmlFor="modelo-nome" className="block font-semibold text-foreground mb-1.5">
            Nome do modelo *
          </label>
          <input
            id="modelo-nome"
            type="text"
            autoFocus
            maxLength={NOME_MAX + 20}
            value={nome}
            onChange={(e) => {
              setNome(e.target.value);
              setErroCampo(null);
            }}
            aria-invalid={erroCampo ? true : undefined}
            aria-describedby={erroCampo ? 'modelo-nome-erro' : undefined}
            placeholder="Ex.: Freezer vertical modelo X"
            className={`w-full bg-secondary border rounded-xl p-3 text-foreground focus:outline-none ${
              erroCampo ? 'border-destructive focus:border-destructive' : 'border-border focus:border-primary'
            }`}
          />
          <div className="flex items-start justify-between gap-2 mt-1">
            {erroCampo ? (
              <p id="modelo-nome-erro" role="alert" className="text-[11px] text-destructive font-semibold">
                {erroCampo}
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">De 1 a 100 caracteres. Não pode repetir um modelo existente.</p>
            )}
            <span className="text-[10px] text-muted-foreground shrink-0">
              {nome.trim().length}/{NOME_MAX}
            </span>
          </div>
          {modeloEdicao && (
            <p className="text-[11px] text-muted-foreground mt-2 bg-secondary/50 p-2.5 rounded-xl border border-border">
              Renomear altera a exibição do modelo também nas OS já existentes e no histórico (a alteração é auditada).
            </p>
          )}
        </div>

        <div className="pt-4 border-t border-border flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={enviando}
            className="px-4 py-2.5 bg-secondary hover:bg-muted text-muted-foreground hover:text-foreground rounded-xl font-semibold cursor-pointer disabled:opacity-60"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={enviando}
            className="px-6 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground font-bold rounded-xl shadow-md shadow-primary/20 cursor-pointer disabled:opacity-60 flex items-center gap-2"
          >
            {enviando && <Loader2 className="w-4 h-4 animate-spin" />}
            {modeloEdicao ? 'Salvar alterações' : 'Cadastrar modelo'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
};
