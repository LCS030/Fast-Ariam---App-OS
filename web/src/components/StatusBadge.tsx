import React from 'react';
import { StatusChamado } from '../types';
import { Clock, PlayCircle, PauseCircle, CheckCircle2, XCircle, Calendar, AlertCircle, HelpCircle } from 'lucide-react';

interface Props {
  /** Valor exato do status da API. */
  status: StatusChamado | string;
  /** Cancelamento é flag (is_cancelled), não status: quando true, o selo mostra "Cancelada". */
  cancelada?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

interface Config {
  label: string;
  bg: string;
  text: string;
  border: string;
  icon: React.ReactNode;
}

const ICON = 'w-3.5 h-3.5';

const CONFIGS: Record<StatusChamado, Config> = {
  Pendente: {
    label: 'Pendente',
    bg: 'bg-amber-500/15',
    text: 'text-amber-500',
    border: 'border-amber-500/30',
    icon: <AlertCircle className={ICON} />,
  },
  Agendado: {
    label: 'Agendado',
    bg: 'bg-primary/15',
    text: 'text-primary-strong',
    border: 'border-primary/30',
    icon: <Calendar className={ICON} />,
  },
  'Em Atendimento': {
    label: 'Em Atendimento',
    bg: 'bg-accent/15',
    text: 'text-accent',
    border: 'border-accent/40',
    icon: <PlayCircle className={ICON} />,
  },
  Pausado: {
    label: 'Pausado',
    bg: 'bg-warning/15',
    text: 'text-warning',
    border: 'border-warning/30',
    icon: <PauseCircle className={ICON} />,
  },
  'Aguardando Reagendamento': {
    label: 'Aguardando Reagendamento',
    bg: 'bg-purple-500/15',
    text: 'text-purple-500',
    border: 'border-purple-500/30',
    icon: <Clock className={ICON} />,
  },
  Finalizado: {
    label: 'Finalizado',
    bg: 'bg-success/15',
    text: 'text-success-strong',
    border: 'border-success/30',
    icon: <CheckCircle2 className={ICON} />,
  },
};

const CONFIG_CANCELADA: Config = {
  label: 'Cancelada',
  bg: 'bg-destructive/15',
  text: 'text-destructive',
  border: 'border-destructive/30',
  icon: <XCircle className={ICON} />,
};

const SIZE_CLASSES = {
  sm: 'px-2 py-0.5 text-xs gap-1',
  md: 'px-2.5 py-1 text-xs font-semibold gap-1.5',
  lg: 'px-3 py-1.5 text-sm font-bold gap-2',
};

export const StatusBadge: React.FC<Props> = ({ status, cancelada = false, size = 'md' }) => {
  // Valor fora do contrato (ex.: legado "Aberto" durante a migração): exibe o texto recebido, sem reinterpretar.
  const config: Config = cancelada
    ? CONFIG_CANCELADA
    : CONFIGS[status as StatusChamado] || {
        label: String(status || 'Sem status'),
        bg: 'bg-secondary',
        text: 'text-muted-foreground',
        border: 'border-border',
        icon: <HelpCircle className={ICON} />,
      };

  return (
    <span
      className={`inline-flex items-center rounded-full border ${config.bg} ${config.text} ${config.border} ${SIZE_CLASSES[size]} whitespace-nowrap`}
    >
      {config.icon}
      <span>{config.label}</span>
    </span>
  );
};
