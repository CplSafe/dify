'use client'

import { createContext, useContext } from 'react'

export type RuntimeContextValue = {
  appId: string
}

export const RuntimeContext = createContext<RuntimeContextValue | null>(null)

export const useRuntimeContext = (): RuntimeContextValue | null =>
  useContext(RuntimeContext)
