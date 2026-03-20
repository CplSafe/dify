import type { OnFeaturesChange } from '@/app/components/base/features/types'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useStore as useAppStore } from '@/app/components/app/store'
import FeatureCard from '@/app/components/base/features/new-feature-panel/feature-card'
import { toast } from '@/app/components/base/ui/toast'
import { updateAppSiteConfig } from '@/service/apps'

type Props = {
  disabled?: boolean
  onChange?: OnFeaturesChange
}

const AnswerDisclaimer = ({
  disabled,
  onChange,
}: Props) => {
  const { t } = useTranslation()
  const appDetail = useAppStore(state => state.appDetail)
  const setAppDetail = useAppStore(state => state.setAppDetail)
  const [saving, setSaving] = useState(false)

  if (!appDetail)
    return null

  const handleChange = async (enabled: boolean) => {
    setSaving(true)
    try {
      const response = await updateAppSiteConfig({
        url: `/apps/${appDetail.id}/site`,
        body: { show_answer_disclaimer: enabled },
      })
      setAppDetail(response)
      onChange?.()
    }
    catch {
      toast.add({
        type: 'error',
        title: t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }),
      })
    }
    finally {
      setSaving(false)
    }
  }

  return (
    <FeatureCard
      icon={(
        <div className="shrink-0 rounded-lg border-[0.5px] border-divider-subtle bg-util-colors-blue-light-blue-light-500 p-1 shadow-xs">
          <span aria-hidden="true" className="i-ri-shield-check-line h-4 w-4 text-text-primary-on-surface" />
        </div>
      )}
      title={t('overview.appInfo.settings.disclaimer.title', { ns: 'appOverview' })}
      value={!!appDetail.site.show_answer_disclaimer}
      description={t('overview.appInfo.settings.disclaimer.desc', { ns: 'appOverview' })}
      tooltip={t('overview.appInfo.settings.disclaimer.tip', { ns: 'appOverview' })}
      onChange={handleChange}
      disabled={disabled || saving}
    />
  )
}

export default AnswerDisclaimer
