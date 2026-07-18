/**
 * NetworkContext - 全局网络链路状态容器
 *
 * 负责监听 API 层发出的网络状态事件，并把“链路断开/恢复”的状态广播给界面。
 * 典型消费方是 `NeuralLinkAlert`，它会在网络异常时显示全屏告警。
 *
 * 新手提示：
 * - `notifyLinkDown()` / `notifyLinkUp()` 位于 `lib/apiError.ts`。
 * - 本 Context 不主动请求后端，只响应全局 CustomEvent。
 * - 普通业务组件通常只需要读取 `isLinkDown`，不需要直接改状态。
 */
'use client';

import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

/**
 * NetworkContext - 网络链路状态管理上下文
 * 
 * 核心职责：
 * - 全局监听网络故障事件
 * - 维护网络链路状态（在线/离线）
 * - 向 NeuralLinkAlert 组件通知状态变化
 * 
 * 事件源：
 * - 'neon-network-down'：由 lib/apiError.ts 的 notifyLinkDown() 发出
 * - 'neon-network-up'：由 lib/apiError.ts 的 notifyLinkUp() 发出
 * 
 * 使用场景：
 * - 当请求超时或服务器错误时，显示全屏红色"网络故障"警告横幅
 * - 当网络恢复时，自动隐藏警告横幅
 */
interface NetworkContextValue {
  /** 网络是否故障（true 表示离线，false 表示在线） */
  isLinkDown: boolean;
  
  /** 手动设置网络状态（通常由事件监听器调用，不建议直接使用） */
  setLinkDown: (v: boolean) => void;
}

export const NetworkContext = createContext<NetworkContextValue>({
  isLinkDown: false,
  setLinkDown: () => {},
});

export function NetworkProvider({ children }: { children: React.ReactNode }) {
  const [isLinkDown, setIsLinkDown] = useState(false);

  useEffect(() => {
    const handleNetworkDown = () => setIsLinkDown(true);
    const handleNetworkUp = () => setIsLinkDown(false);

    window.addEventListener('neon-network-down', handleNetworkDown);
    window.addEventListener('neon-network-up', handleNetworkUp);

    return () => {
      window.removeEventListener('neon-network-down', handleNetworkDown);
      window.removeEventListener('neon-network-up', handleNetworkUp);
    };
  }, []);

  const contextValue = useMemo(
    () => ({ isLinkDown, setLinkDown: setIsLinkDown }),
    [isLinkDown]
  );

  return (
    <NetworkContext.Provider value={contextValue}>
      {children}
    </NetworkContext.Provider>
  );
}

export function useNetwork(): NetworkContextValue {
  return useContext(NetworkContext);
}
