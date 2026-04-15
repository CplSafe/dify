import type { ReactNode } from 'react'
import * as React from 'react'
import { AppInitializer } from '@/app/components/app-initializer'
import AmplitudeProvider from '@/app/components/base/amplitude'
import GA, { GaType } from '@/app/components/base/ga'
import CreatorSidebar from '@/app/components/creator/sidebar'
import TaskCenterButton from '@/app/components/creator/task-center'
import { AppContextProvider } from '@/context/app-context-provider'
import { EventEmitterContextProvider } from '@/context/event-emitter-provider'
import { ModalContextProvider } from '@/context/modal-context-provider'
import { ProviderContextProvider } from '@/context/provider-context-provider'

const CreatorLayout = ({ children }: { children: ReactNode }) => {
  return (
    <>
      <GA gaType={GaType.admin} />
      <AmplitudeProvider />
      <AppInitializer>
        <AppContextProvider>
          <EventEmitterContextProvider>
            <ProviderContextProvider>
              <ModalContextProvider>
                <div className="flex h-screen overflow-hidden bg-background-body">
                  <CreatorSidebar />
                  <main className="relative flex flex-1 flex-col overflow-hidden">
                    {/* Top-right toolbar: task center */}
                    <div className="absolute top-3 right-4 z-40 flex items-center gap-1">
                      <TaskCenterButton />
                    </div>
                    {children}
                  </main>
                </div>
              </ModalContextProvider>
            </ProviderContextProvider>
          </EventEmitterContextProvider>
        </AppContextProvider>
      </AppInitializer>
    </>
  )
}

export default CreatorLayout
