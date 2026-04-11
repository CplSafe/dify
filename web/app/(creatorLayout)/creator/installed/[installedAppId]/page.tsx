import * as React from 'react'
import CreatorInstalledApp from '@/app/components/creator/installed-app-page'

type CreatorInstalledAppPageProps = {
  params?: Promise<{
    installedAppId: string
  }>
}

async function CreatorInstalledAppPage({ params }: CreatorInstalledAppPageProps) {
  const { installedAppId } = await (params ?? Promise.reject(new Error('Missing params')))

  return <CreatorInstalledApp installedAppId={installedAppId} />
}

export default CreatorInstalledAppPage
