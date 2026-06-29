import type { ReactNode } from 'react'
import * as React from 'react'
import { AppInitializer } from '@/app/components/app-initializer'
import Header from '@/app/components/header'
import HeaderWrapper from '@/app/components/header/header-wrapper'
import { AppContextProvider } from '@/context/app-context-provider'
import { EventEmitterContextProvider } from '@/context/event-emitter-provider'
import { ModalContextProvider } from '@/context/modal-context-provider'
import { ProviderContextProvider } from '@/context/provider-context-provider'
import RoleRouteGuard from './role-route-guard'

const Layout = ({ children }: { children: ReactNode }) => {
  return (
    <>
      <AppInitializer>
        <AppContextProvider>
          <EventEmitterContextProvider>
            <ProviderContextProvider>
              <ModalContextProvider>
                <HeaderWrapper>
                  <Header />
                </HeaderWrapper>
                <RoleRouteGuard>
                  {children}
                </RoleRouteGuard>
              </ModalContextProvider>
            </ProviderContextProvider>
          </EventEmitterContextProvider>
        </AppContextProvider>
      </AppInitializer>
    </>
  )
}
export default Layout
