/**
 * ClientShell - 客户端容器和全局 Provider 嵌套
 * 
 * 核心职责：
 * 1. 组织整个应用的 React Provider 层次结构
 * 2. 实现错误边界捕获意外崩溃
 * 3. 鉴权检查和条件化 Provider 挂载
 * 4. 提供全局背景粒子效果
 * 5. 实时网络状态监控
 * 
 * 架构层次（从内到外）：
 * ClientShell（最外层容器）
 *  └─ ErrorBoundary（全局错误捕获）
 *      └─ NetworkProvider（网络状态监控）
 *          ├─ CyberParticles（背景粒子效果）
 *          ├─ AuthGuard（鉴权检查）
 *          │   └─ AuthenticatedShell（仅在认证后挂载）
 *          │       ├─ SettingsProvider（全局配置）
 *          │       ├─ LogProvider（系统日志）
 *          │       └─ AiSidebar（AI 助手侧栏）
 *          └─ NeuralLinkAlert（网络离线警告横幅）
 * 
 * Provider 挂载策略：
 * - 登录页（/auth/login）：仅挂载 NetworkProvider，跳过其他 Provider
 * - 已认证页面：挂载完整的 Provider 层次
 * 原因：避免登录页的 SettingsProvider/LogProvider 发起周期性 API 请求导致 401 错误
 * 
 * @component
 */

'use client';

import React, { ReactNode } from 'react';
import { NetworkProvider } from '@/context/NetworkContext';
import { SettingsProvider } from '@/context/SettingsContext';
import { LogProvider } from '@/context/LogContext';
import NeuralLinkAlert from '@/components/common/NeuralLinkAlert';
import AuthGuard from '@/components/common/AuthGuard';
import AiSidebar from '@/components/ai/AiSidebar';
import CyberParticles from '@/components/common/CyberParticles';

/**
 * ErrorBoundary - React 错误边界组件
 * 
 * 职责：
 * - 捕获子组件树中的任何 JavaScript 错误
 * - 防止错误向上传播导致整个应用崩溃
 * - 显示友好的错误界面和刷新按钮
 * 
 * 工作流程：
 * 1. 捕获错误时 → 保存到 state
 * 2. getDerivedStateFromError 同步更新状态
 * 3. componentDidCatch 记录错误到控制台
 * 4. render 显示错误界面（替代原 children）
 * 5. 用户点击"刷新页面"按钮 → window.location.reload()
 */
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

/**
 * AuthenticatedShell — 只在 AuthGuard 确认认证后才挂载的 Provider 层
 *
 * 挂载语义：AuthGuard 可选 authenticatedWrapper（本处为 AuthenticatedShell）。
 * - /auth/login：仅渲染 children，不挂载 SettingsProvider / LogProvider / AiSidebar
 * - 已认证：以 AuthenticatedShell 包裹 children，再注入设置、日志与侧栏上下文
 * 目的：未登录态不发起依赖鉴权的 Provider 轮询，压缩无效 401 与日志噪声
 */
function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  return (
    <SettingsProvider>
      <LogProvider>
        {children}
        <AiSidebar />
      </LogProvider>
    </SettingsProvider>
  );
}

export default function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <NetworkProvider>
        <CyberParticles />
        {/*
          authenticatedWrapper=AuthenticatedShell：
          - AuthGuard 在 /auth/login 时直接渲染裸 children（登录页），跳过 AuthenticatedShell
          - AuthGuard 在 isAuthenticated=true 时才用 AuthenticatedShell 包裹 children
          - SettingsProvider / LogProvider / AiSidebar 因此只在认证后挂载
        */}
        <AuthGuard authenticatedWrapper={AuthenticatedShell}>
          {children}
        </AuthGuard>
        <NeuralLinkAlert />
      </NetworkProvider>
    </ErrorBoundary>
  );
}
