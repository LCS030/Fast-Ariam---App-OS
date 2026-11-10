import React, { useState } from 'react';
import { UsuarioSessao } from '../types';
import { LogoFast } from '../components/LogoFast';
import { ChamadoService } from '../services/chamadoService';
import { mensagemErro } from '../utils/os';
import {
  Shield,
  ArrowRight,
  Lock,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  Loader2,
} from 'lucide-react';

interface Props {
  onLoginSuccess: (usuario: UsuarioSessao) => void;
  /** Aviso exibido quando a sessão foi encerrada (ex.: 401). */
  aviso?: string | null;
}

export const LoginView: React.FC<Props> = ({ onLoginSuccess, aviso }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setErrorMessage('Por favor, informe seu e-mail e senha.');
      return;
    }

    setLoading(true);
    setErrorMessage(null);

    try {
      const user = await ChamadoService.login(email.trim(), password);
      onLoginSuccess(user);
    } catch (err) {
      setErrorMessage(mensagemErro(err, 'Falha na autenticação. Verifique suas credenciais e tente novamente.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center p-4 relative overflow-hidden text-foreground font-sans select-none">
      {/* Main Login Card */}
      <div className="w-full max-w-md bg-card border border-border rounded-3xl p-8 shadow-xl relative z-10">
        {/* Marca: logo oficial FAST Gôndolas & Check-outs (a mesma do app) */}
        <div className="text-center mb-7">
          <h1 className="sr-only">FAST Gôndolas & Check-outs</h1>
          <LogoFast className="h-16 mx-auto" />
          <p className="text-xs text-muted-foreground mt-4">Sistema de Gestão de Ordens de Serviço</p>
        </div>

        {aviso && !errorMessage && (
          <div role="status" className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-700 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{aviso}</span>
          </div>
        )}

        {errorMessage && (
          <div className="mb-4 p-3 bg-destructive/10 border border-destructive/30 rounded-xl text-destructive text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold">Não foi possível autenticar</p>
              <p className="text-[11px] mt-0.5 opacity-90">{errorMessage}</p>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1.5">
              E-mail de Acesso
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 absolute left-3.5 top-3.5 text-muted-foreground" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="seu.email@empresa.com.br"
                autoComplete="email"
                className="w-full bg-secondary border border-border rounded-xl py-2.5 pl-10 pr-4 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-foreground mb-1.5">
              Senha
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 absolute left-3.5 top-3.5 text-muted-foreground" />
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Digite sua senha"
                autoComplete="current-password"
                className="w-full bg-secondary border border-border rounded-xl py-2.5 pl-10 pr-10 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-3.5 text-muted-foreground hover:text-foreground cursor-pointer"
                title={showPassword ? 'Ocultar senha' : 'Exibir senha'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-primary hover:bg-primary/90 text-primary-foreground font-extrabold text-xs rounded-xl shadow-lg shadow-primary/25 flex items-center justify-center gap-2 transition-all cursor-pointer disabled:opacity-70"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Autenticando...</span>
              </>
            ) : (
              <>
                <span>Entrar no Sistema</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        {/* Security Footer */}
        <div className="mt-6 pt-4 border-t border-border text-center">
          <p className="text-[10px] text-muted-foreground flex items-center justify-center gap-1">
            <Shield className="w-3 h-3 text-primary-strong" /> FAST Gôndolas & Check-outs • Acesso Seguro
          </p>
        </div>
      </div>
    </div>
  );
};
