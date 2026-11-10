import { LogoFast } from './components/LogoFast';
import React, { useState, useEffect } from 'react';
import { UsuarioSessao } from './types';
import { ChamadoService } from './services/chamadoService';
import { apiClient } from './services/apiClient';
import { LoginView } from './views/LoginView';
import { AdminDashboardView } from './views/AdminDashboardView';
import { Shield, Smartphone, LogOut, Ban } from 'lucide-react';

export function App() {
  const [user, setUser] = useState<UsuarioSessao | null>(() => ChamadoService.getUsuarioLogado());
  const [avisoSessao, setAvisoSessao] = useState<string | null>(null);

  useEffect(() => {
    // 401 em qualquer chamada: o token já foi descartado pelo cliente HTTP; volta ao login com aviso.
    apiClient.setOnUnauthorized(() => {
      setUser(null);
      setAvisoSessao('Sua sessão expirou ou o acesso foi revogado. Entre novamente.');
    });
    return () => apiClient.setOnUnauthorized(null);
  }, []);

  // Atualiza o nome exibido com GET /api/auth/me (falha silenciosa: mantém o nome derivado do token).
  const idUsuario = user?.id_tecnico;
  useEffect(() => {
    if (!user) return;
    let ativo = true;
    ChamadoService.atualizarPerfil(user).then((atualizado) => {
      if (ativo && atualizado.nome !== user.nome) setUser(atualizado);
    });
    return () => {
      ativo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idUsuario]);

  const handleLoginSuccess = (usr: UsuarioSessao) => {
    setAvisoSessao(null);
    setUser(usr);
  };

  const handleLogout = () => {
    ChamadoService.logout();
    setAvisoSessao(null);
    setUser(null);
  };

  if (!user) {
    return <LoginView onLoginSuccess={handleLoginSuccess} aviso={avisoSessao} />;
  }

  // RF-03: técnico no painel web vê apenas uma tela informativa, sem acesso administrativo.
  // (A API continua sendo a autoridade: ela recusa com 403 qualquer rota administrativa para o técnico.)
  if (user.role === 'tecnico') {
    return (
      <div className="min-h-screen bg-background flex flex-col justify-center items-center p-4 text-foreground font-sans">
        <div className="w-full max-w-lg bg-card border border-border rounded-3xl p-8 shadow-2xl text-center space-y-6">
          <LogoFast className="h-12 mx-auto" />

          <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 text-primary-strong flex items-center justify-center mx-auto shadow-md">
            <Smartphone className="w-8 h-8 text-primary-strong" />
          </div>

          <div className="space-y-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-primary-strong px-3 py-1 bg-primary/10 rounded-full border border-primary/20">
              Acesso de técnico de campo
            </span>
            <h1 className="text-xl font-black text-foreground font-['Space_Grotesk']">
              Painel exclusivo para administradores
            </h1>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Olá, <strong className="text-foreground">{user.nome}</strong>. O painel web da FAST Gôndolas & Check-outs é
              dedicado à gestão administrativa. Seu perfil não tem acesso a esta área.
            </p>
          </div>

          <div className="bg-secondary/60 p-4 rounded-2xl border border-border text-left text-xs space-y-2">
            <div className="flex items-center gap-2 font-bold text-foreground">
              <Shield className="w-4 h-4 text-primary-strong" />
              <span>Como executar seus atendimentos:</span>
            </div>
            <p className="text-muted-foreground text-[11px]">
              Utilize o <strong>aplicativo Android da FAST</strong> para consultar suas OS, registrar deslocamentos, serviços,
              fotos e a assinatura do cliente.
            </p>
          </div>

          <button
            onClick={handleLogout}
            className="w-full py-3 bg-secondary hover:bg-muted text-foreground border border-border rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <LogOut className="w-4 h-4 text-muted-foreground" />
            <span>Sair</span>
          </button>
        </div>
      </div>
    );
  }

  if (user.role !== 'admin') {
    return (
      <div className="min-h-screen bg-background flex flex-col justify-center items-center p-4 text-foreground font-sans">
        <div className="w-full max-w-md bg-card border border-border rounded-3xl p-8 shadow-2xl text-center space-y-4">
          <Ban className="w-10 h-10 text-destructive mx-auto" />
          <h1 className="text-lg font-black font-['Space_Grotesk']">Perfil sem acesso ao painel</h1>
          <p className="text-xs text-muted-foreground">O seu perfil de acesso não é reconhecido por este painel.</p>
          <button
            onClick={handleLogout}
            className="w-full py-3 bg-secondary hover:bg-muted border border-border rounded-xl text-xs font-bold cursor-pointer"
          >
            Sair
          </button>
        </div>
      </div>
    );
  }

  return <AdminDashboardView onLogout={handleLogout} />;
}

export default App;
