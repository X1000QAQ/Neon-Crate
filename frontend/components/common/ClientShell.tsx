'use client';

import { NetworkProvider } from '@/context/NetworkContext';
import NeuralLinkAlert from '@/components/common/NeuralLinkAlert';
import AuthGuard from '@/components/common/AuthGuard';
import AiSidebar from '@/components/ai/AiSidebar';
import CyberParticles from '@/components/common/CyberParticles';

export default function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <NetworkProvider>
      <CyberParticles />
      <AuthGuard>
        {children}
        <AiSidebar />
      </AuthGuard>
      <NeuralLinkAlert />
    </NetworkProvider>
  );
}
