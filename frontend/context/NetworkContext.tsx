'use client';

import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

interface NetworkContextValue {
  isLinkDown: boolean;
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
