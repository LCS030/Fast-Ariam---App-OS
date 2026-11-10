import React, { useState, useEffect } from 'react';
import { Cliente } from '../types';
import { Building, MapPin, Phone, User, Hash, Loader2 } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';

interface Props {
  isOpen: boolean;
  clienteEdicao?: Cliente | null;
  onClose: () => void;
  onSave: (data: Partial<Cliente>) => Promise<void>;
}

const INPUT = 'w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none';
const INPUT_CARD = 'w-full bg-card border border-border rounded-xl p-2.5 text-foreground focus:border-primary focus:outline-none';

export const ModalCliente: React.FC<Props> = ({ isOpen, clienteEdicao, onClose, onSave }) => {
  const [razaoSocial, setRazaoSocial] = useState('');
  const [codigo, setCodigo] = useState('');
  const [contatoNome, setContatoNome] = useState('');
  const [contatoTelefone, setContatoTelefone] = useState('');
  const [telefone, setTelefone] = useState('');
  const [endereco, setEndereco] = useState('');
  const [numero, setNumero] = useState('');
  const [bairro, setBairro] = useState('');
  const [cidade, setCidade] = useState('');
  const [uf, setUf] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const { enviando, erro, executar, limparErro } = useAcaoAssincrona();

  const idEdicao = clienteEdicao?.id_cliente;

  useEffect(() => {
    setErroLocal(null);
    limparErro();
    setRazaoSocial(clienteEdicao?.razao_social || '');
    setCodigo(clienteEdicao?.codigo !== undefined && clienteEdicao?.codigo !== null ? String(clienteEdicao.codigo) : '');
    setContatoNome(clienteEdicao?.contato_principal_nome || '');
    setContatoTelefone(clienteEdicao?.contato_principal_telefone || '');
    setTelefone(clienteEdicao?.telefone || '');
    setEndereco(clienteEdicao?.endereco || '');
    setNumero(clienteEdicao?.numero || '');
    setBairro(clienteEdicao?.bairro || '');
    setCidade(clienteEdicao?.cidade || '');
    setUf(clienteEdicao?.uf || '');
    setIsActive(clienteEdicao ? clienteEdicao.is_active !== false : true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, idEdicao]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!razaoSocial.trim()) return setErroLocal('Informe a razão social do cliente.');
    // RN-04: código numérico obrigatório, digitado pelo administrador (vem de outro sistema).
    if (!/^\d+$/.test(codigo.trim())) {
      return setErroLocal('Informe o código do cliente (somente números inteiros).');
    }
    if (!telefone.trim()) return setErroLocal('Informe o telefone do cliente.');
    if (!endereco.trim() || !numero.trim() || !bairro.trim() || !cidade.trim()) {
      return setErroLocal('Preencha logradouro, número, bairro e cidade.');
    }
    if (!/^[A-Za-z]{2}$/.test(uf.trim())) return setErroLocal('A UF deve ter exatamente 2 letras (ex.: ES).');
    setErroLocal(null);

    const ok = await executar(() =>
      onSave({
        id_cliente: clienteEdicao?.id_cliente,
        razao_social: razaoSocial.trim(),
        codigo: Number(codigo.trim()),
        contato_principal_nome: contatoNome.trim() || undefined,
        contato_principal_telefone: contatoTelefone.trim() || undefined,
        telefone: telefone.trim(),
        endereco: endereco.trim(),
        numero: numero.trim(),
        bairro: bairro.trim(),
        cidade: cidade.trim(),
        uf: uf.trim().toUpperCase(),
        is_active: isActive,
      })
    );
    if (ok) onClose();
  };

  return (
    <ModalShell
      titulo={clienteEdicao ? `Editar cliente: ${clienteEdicao.razao_social}` : 'Cadastrar novo cliente'}
      subtitulo="Dados cadastrais e endereço do cliente"
      icone={<Building className="w-5 h-5" />}
      onClose={onClose}
      erro={erro}
      larguraMax="max-w-2xl"
    >
      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        {erroLocal && (
          <div role="alert" className="p-3 bg-destructive/10 border border-destructive/30 rounded-xl text-destructive font-semibold">
            {erroLocal}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="sm:col-span-2">
            <label htmlFor="cli-razao" className="block font-semibold text-foreground mb-1">Razão social / nome da empresa *</label>
            <input id="cli-razao" type="text" required value={razaoSocial} onChange={(e) => setRazaoSocial(e.target.value)} className={INPUT} />
          </div>
          <div>
            <label htmlFor="cli-codigo" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
              <Hash className="w-3.5 h-3.5 text-primary-strong" /> Código do cliente *
            </label>
            <input
              id="cli-codigo"
              type="text"
              inputMode="numeric"
              required
              value={codigo}
              onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))}
              className={INPUT}
            />
            <p className="text-[10px] text-muted-foreground mt-1">Único; vem do sistema de origem.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label htmlFor="cli-tel" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
              <Phone className="w-3.5 h-3.5 text-primary-strong" /> Telefone geral *
            </label>
            <input id="cli-tel" type="text" required value={telefone} onChange={(e) => setTelefone(e.target.value)} className={INPUT} />
          </div>
          <div>
            <label htmlFor="cli-contato" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
              <User className="w-3.5 h-3.5 text-primary-strong" /> Contato principal
            </label>
            <input id="cli-contato" type="text" value={contatoNome} onChange={(e) => setContatoNome(e.target.value)} className={INPUT} />
          </div>
          <div>
            <label htmlFor="cli-contato-tel" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
              <Phone className="w-3.5 h-3.5 text-primary-strong" /> Tel. do contato
            </label>
            <input id="cli-contato-tel" type="text" value={contatoTelefone} onChange={(e) => setContatoTelefone(e.target.value)} className={INPUT} />
          </div>
        </div>

        <div className="bg-secondary/50 p-4 rounded-2xl border border-border space-y-3">
          <h4 className="font-bold text-foreground text-xs flex items-center gap-1.5">
            <MapPin className="w-4 h-4 text-primary-strong" /> Endereço de atendimento
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label htmlFor="cli-end" className="block text-[11px] text-muted-foreground mb-1">Logradouro / rua *</label>
              <input id="cli-end" type="text" required value={endereco} onChange={(e) => setEndereco(e.target.value)} className={INPUT_CARD} />
            </div>
            <div>
              <label htmlFor="cli-num" className="block text-[11px] text-muted-foreground mb-1">Número *</label>
              <input id="cli-num" type="text" required value={numero} onChange={(e) => setNumero(e.target.value)} className={INPUT_CARD} />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label htmlFor="cli-bairro" className="block text-[11px] text-muted-foreground mb-1">Bairro *</label>
              <input id="cli-bairro" type="text" required value={bairro} onChange={(e) => setBairro(e.target.value)} className={INPUT_CARD} />
            </div>
            <div>
              <label htmlFor="cli-cidade" className="block text-[11px] text-muted-foreground mb-1">Cidade *</label>
              <input id="cli-cidade" type="text" required value={cidade} onChange={(e) => setCidade(e.target.value)} className={INPUT_CARD} />
            </div>
            <div>
              <label htmlFor="cli-uf" className="block text-[11px] text-muted-foreground mb-1">UF (2 letras) *</label>
              <input
                id="cli-uf"
                type="text"
                required
                maxLength={2}
                value={uf}
                onChange={(e) => setUf(e.target.value.replace(/[^a-zA-Z]/g, '').toUpperCase())}
                className={`${INPUT_CARD} font-bold uppercase`}
              />
            </div>
          </div>
        </div>

        {clienteEdicao && (
          <div className="bg-secondary/40 border border-border rounded-2xl p-3.5 flex items-center justify-between">
            <div>
              <span className="font-bold text-xs text-foreground block">Situação do cadastro</span>
              <span className="text-[11px] text-muted-foreground">
                {isActive
                  ? 'Cliente ativo: disponível para novas OS.'
                  : 'Cliente inativo (desativação lógica): não recebe novas OS; o histórico é mantido.'}
              </span>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="w-4 h-4 rounded bg-secondary border-border accent-emerald-500 cursor-pointer"
              />
              <span className={`text-xs font-bold ${isActive ? 'text-success-strong' : 'text-muted-foreground'}`}>
                {isActive ? 'Ativo' : 'Inativo'}
              </span>
            </label>
          </div>
        )}

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
            {clienteEdicao ? 'Salvar alterações' : 'Cadastrar cliente'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
};
