'use client';

import React, { ReactNode } from 'react';
import { NetworkProvider } from '@/context/NetworkContext';
import { SettingsProvider } from '@/context/SettingsContext';
import { LogProvider } from '@/context/LogContext';
import NeuralLinkAlert from '@/components/common/NeuralLinkAlert';
import AuthGuard from '@/components/common/AuthGuard';
import AiSidebar from '@/components/ai/AiSidebar';
import CyberParticles from '@/components/common/CyberParticles';

class ErrorBoundary extends React.Component<
  { children: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          backgroundColor: '#0a0e27',
          color: '#fff',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}>
          <div style={{ textAlign: 'center', padding: '20px' }}>
            <h1 style={{ fontSize: '32px', marginBottom: '16px' }}>⚠️ 应用崩溃</h1>
            <p style={{ fontSize: '16px', marginBottom: '24px', color: '#ccc' }}>
              {this.state.error?.message || '发生未知错误'}
            </p>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: '10px 20px',
                fontSize: '16px',
                backgroundColor: '#00d4ff',
                color: '#000',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold',
              }}
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <NetworkProvider>
        <SettingsProvider>
          <LogProvider>
            <CyberParticles />
            <AuthGuard>
              {children}
              <AiSidebar />
            </AuthGuard>
            <NeuralLinkAlert />
          </LogProvider>
        </SettingsProvider>
      </NetworkProvider>
    </ErrorBoundary>
  );
}
