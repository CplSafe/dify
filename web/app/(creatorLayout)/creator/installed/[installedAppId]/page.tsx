import CreatorInstalledApp from '@/app/components/creator/installed-app-page'

type Props = {
  params: Promise<{ installedAppId: string }>
  searchParams?: Promise<{ conversationId?: string }>
}

export default async function CreatorInstalledAppPage({
  params,
  searchParams,
}: Props) {
  const { installedAppId } = await params
  const resolved = await (searchParams
    ?? Promise.resolve({ conversationId: undefined }))
  const conversationId = resolved?.conversationId

  return (
    <CreatorInstalledApp
      installedAppId={installedAppId}
      resumeConversationId={conversationId}
    />
  )
}
