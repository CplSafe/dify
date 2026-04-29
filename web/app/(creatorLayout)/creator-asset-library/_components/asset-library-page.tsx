'use client'

import { useTranslation } from 'react-i18next'

export default function AssetLibraryPage() {
  const { t } = useTranslation('assetLibrary')

  return (
    <div className="flex h-full flex-col px-8 py-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
    </div>
  )
}
