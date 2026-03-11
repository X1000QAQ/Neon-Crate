'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';

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
    (window as any).__setLinkDown = setIsLinkDown;
    return () => {
      delete (window as any).__setLinkDown;
    };
  }, []);

  return (
    <NetworkContext.Provider value={{ isLinkDown, setLinkDown: setIsLinkDown }}>
      {children}
    </NetworkContext.Provider>
  );
}

export function useNetwork(): NetworkContextValue {
  return useContext(NetworkContext);
}
