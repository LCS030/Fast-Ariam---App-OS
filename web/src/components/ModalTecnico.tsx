import React, { useState, useEffect } from 'react';
import { Tecnico, UserRole } from '../types';
import { TecnicoPayload } from '../services/apiClient';
import { Wrench, Mail, Phone, CreditCard, Shield, Lock, FileText, Loader2 } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';

interface Props {
  isOpen: boolean;
  tecnicoEdicao?: Tecnico | null;
  onClose: () => void;
  onSave: (data: TecnicoPayload & { id_tecnico?: number }) => Promise<void>;
}

const INPUT = 'w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none';
const INPUT_CARD = 'w-full bg-card border border-border rounded-xl p-2.5 text-foreground focus:border-primary focus:outline-none';

const apenasDigitos = (v: string) => v.replace(/\D/g, '');

export const ModalTecnico: React.FC<Props> = ({ isOpen, tecnicoEdicao, onClose, onSave }) => {
  const [nome, setNome] = useState('');
  const [email, setEmail] = useState('');
  const [cpf, setCpf] = useState('');
  const [cnpj, setCnpj] = useState('');
  const [inscricaoEstadual, setInscricaoEstadual] = useState('');
  const [telefone, setTelefone] = useState('');
  const [role, setRole] = useState<UserRole>('tecnico');
  const [password, setPassword] = useState('');
  const [banco, setBanco] = useState('');
  const [agencia, setAgencia] = useState('');
  const [conta, setConta] = useState('');
  const [pix, setPix] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const { enviando, erro, executar, limparErro } = useAcaoAssincrona();

  const idEdicao = tecnicoEdicao?.id_tecnico;

  useEffect(() => {
    setErroLocal(null);
    limparErro();
    setNome(tecnicoEdicao?.nome || '');
    setEmail(tecnicoEdicao?.email || '');
    setCpf(tecnicoEdicao?.cpf || '');
    setCnpj(tecnicoEdicao?.cnpj || '');
    setInscricaoEstadual(tecnicoEdicao?.inscricao_estadual || '');
    setTelefone(tecnicoEdicao?.telefone || '');
    setRole((tecnicoEdicao?.role as UserRole) || 'tecnico');
    setPassword('');
    setBanco(tecnicoEdicao?.dados_bancarios?.banco || '');
    setAgencia(tecnicoEdicao?.dados_bancarios?.agencia || '');
    setConta(tecnicoEdicao?.dados_bancarios?.conta || '');
    setPix(tecnicoEdicao?.dados_bancarios?.pix || '');
    setIsActive(tecnicoEdicao ? tecnicoEdicao.is_active !== false : true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, idEdicao]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nome.trim() || !email.trim()) return setErroLocal('Informe nome e e-mail.');
    // Na edição, CPF/CNPJ só são validados e enviados se o campo foi alterado.
    const cpfAlterado = !tecnicoEdicao || cpf.trim() !== (tecnicoEdicao.cpf || '').trim();
    const cnpjAlterado = !tecnicoEdicao || cnpj.trim() !== (tecnicoEdicao.cnpj || '').trim();
    if (cpfAlterado && apenasDigitos(cpf).length !== 11) return setErroLocal('Informe um CPF com 11 dígitos.');
    if (cnpjAlterado && apenasDigitos(cnpj).length !== 14) {
      return setErroLocal('Informe um CNPJ com 14 dígitos (obrigatório e único).');
    }
    if (!telefone.trim()) return setErroLocal('Informe o telefone do técnico.');
    if (!tecnicoEdicao && !password) return setErroLocal('Defina a senha inicial de acesso do técnico.');

    // RN-07: banco, agência e conta obrigatórios no cadastro. Na edição de cadastro antigo sem dados
    // bancários, só envia o bloco se ele for preenchido por completo.
    const algumBancario = banco.trim() || agencia.trim() || conta.trim();
    const todosBancarios = banco.trim() && agencia.trim() && conta.trim();
    if (!tecnicoEdicao && !todosBancarios) {
      return setErroLocal('Informe banco, agência e conta (dados bancários são obrigatórios).');
    }
    if (tecnicoEdicao && algumBancario && !todosBancarios) {
      return setErroLocal('Dados bancários incompletos: preencha banco, agência e conta.');
    }
    setErroLocal(null);

    const payload: TecnicoPayload & { id_tecnico?: number } = {
      id_tecnico: tecnicoEdicao?.id_tecnico,
      nome: nome.trim(),
      email: email.trim(),
      cpf: cpfAlterado ? cpf.trim() : undefined,
      cnpj: cnpjAlterado ? cnpj.trim() : undefined,
      inscricao_estadual: inscricaoEstadual.trim() || undefined,
      telefone: telefone.trim(),
      role,
    };
    if (todosBancarios) {
      payload.dados_bancarios = {
        banco: banco.trim(),
        agencia: agencia.trim(),
        conta: conta.trim(),
        pix: pix.trim() || undefined,
      };
    }
    if (tecnicoEdicao) {
      payload.is_active = isActive;
    } else {
      payload.password = password;
    }

    const ok = await executar(() => onSave(payload));
    if (ok) onClose();
  };

  return (
    <ModalShell
      titulo={tecnicoEdicao ? `Editar técnico: ${tecnicoEdicao.nome}` : 'Cadastrar novo técnico'}
      subtitulo="Dados profissionais, fiscais, credenciais e dados bancários (somente administradores)"
      icone={<Wrench className="w-5 h-5" />}
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

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="tec-nome" className="block font-semibold text-foreground mb-1">Nome completo *</label>
            <input id="tec-nome" type="text" required value={nome} onChange={(e) => setNome(e.target.value)} className={INPUT} />
          </div>
          <div>
            <label htmlFor="tec-email" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
              <Mail className="w-3.5 h-3.5 text-primary-strong" /> E-mail (login) *
            </label>
            <input id="tec-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label htmlFor="tec-cpf" className="block font-semibold text-foreground mb-1">CPF *</label>
            <input
              id="tec-cpf"
              type="text"
              required
              maxLength={14}
              placeholder="000.000.000-00"
              value={cpf}
              onChange={(e) => setCpf(e.target.value)}
              className={INPUT}
            />
          </div>
          <div>
            <label htmlFor="tec-cnpj" className="block font-semibold text-foreground mb-1">CNPJ *</label>
            <input
              id="tec-cnpj"
              type="text"
              required
              maxLength={18}
              placeholder="00.000.000/0000-00"
              value={cnpj}
              onChange={(e) => setCnpj(e.target.value)}
              className={INPUT}
            />
          </div>
          <div>
            <label htmlFor="tec-tel" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
              <Phone className="w-3.5 h-3.5 text-primary-strong" /> Telefone *
            </label>
            <input id="tec-tel" type="text" required value={telefone} onChange={(e) => setTelefone(e.target.value)} className={INPUT} />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label htmlFor="tec-ie" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
              <FileText className="w-3.5 h-3.5 text-primary-strong" /> Inscrição estadual
            </label>
            <input id="tec-ie" type="text" value={inscricaoEstadual} onChange={(e) => setInscricaoEstadual(e.target.value)} className={INPUT} />
          </div>
          <div>
            <label htmlFor="tec-role" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
              <Shield className="w-3.5 h-3.5 text-primary-strong" /> Papel / perfil *
            </label>
            <select
              id="tec-role"
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              className={`${INPUT} cursor-pointer`}
            >
              <option value="tecnico">Técnico de campo</option>
              <option value="admin">Administrador</option>
            </select>
          </div>
          {!tecnicoEdicao && (
            <div>
              <label htmlFor="tec-senha" className="block font-semibold text-foreground mb-1 flex items-center gap-1">
                <Lock className="w-3.5 h-3.5 text-primary-strong" /> Senha inicial *
              </label>
              <input
                id="tec-senha"
                type="password"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={INPUT}
              />
            </div>
          )}
        </div>

        <div className="bg-secondary/50 p-4 rounded-2xl border border-border space-y-3">
          <h4 className="font-bold text-foreground text-xs flex items-center gap-1.5">
            <CreditCard className="w-4 h-4 text-primary-strong" /> Dados bancários da conta jurídica
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div>
              <label htmlFor="tec-banco" className="block text-[11px] text-muted-foreground mb-1">Banco {!tecnicoEdicao && '*'}</label>
              <input id="tec-banco" type="text" value={banco} onChange={(e) => setBanco(e.target.value)} className={INPUT_CARD} />
            </div>
            <div>
              <label htmlFor="tec-agencia" className="block text-[11px] text-muted-foreground mb-1">Agência {!tecnicoEdicao && '*'}</label>
              <input id="tec-agencia" type="text" value={agencia} onChange={(e) => setAgencia(e.target.value)} className={INPUT_CARD} />
            </div>
            <div>
              <label htmlFor="tec-conta" className="block text-[11px] text-muted-foreground mb-1">Conta corrente {!tecnicoEdicao && '*'}</label>
              <input id="tec-conta" type="text" value={conta} onChange={(e) => setConta(e.target.value)} className={INPUT_CARD} />
            </div>
            <div>
              <label htmlFor="tec-pix" className="block text-[11px] text-muted-foreground mb-1">Chave Pix (opcional)</label>
              <input id="tec-pix" type="text" value={pix} onChange={(e) => setPix(e.target.value)} className={INPUT_CARD} />
            </div>
          </div>
        </div>

        {tecnicoEdicao && (
          <div className="bg-secondary/40 border border-border rounded-2xl p-3.5 flex items-center justify-between">
            <div>
              <span className="font-bold text-xs text-foreground block">Situação do cadastro</span>
              <span className="text-[11px] text-muted-foreground">
                {isActive
                  ? 'Técnico ativo: elegível para atribuição de OS.'
                  : 'Técnico inativo: perde o acesso ao aplicativo e não recebe novas OS.'}
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
            {tecnicoEdicao ? 'Salvar alterações' : 'Cadastrar técnico'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
};
