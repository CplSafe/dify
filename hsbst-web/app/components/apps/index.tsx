'use client'

import AppListContext from '@/context/app-list-context'
import useDocumentTitle from '@/hooks/use-document-title'
import List from './list'

const Apps = () => {
  useDocumentTitle('我的应用')

  return (
    <AppListContext.Provider value={{
      currentApp: undefined,
      isShowTryAppPanel: false,
      setShowTryAppPanel: () => undefined,
      controlHideCreateFromTemplatePanel: 0,
    }}
    >
      <div className="relative flex h-0 shrink-0 grow flex-col overflow-y-auto bg-background-body">
        <List />
      </div>
    </AppListContext.Provider>
  )
}

export default Apps
