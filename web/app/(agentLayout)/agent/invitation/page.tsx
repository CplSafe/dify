'use client'

import { QRCodeSVG } from 'qrcode.react'
import * as React from 'react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/app/components/base/ui/toast'
import {
  useAgentInvitations,
  useGenerateInvitation,
} from '@/service/use-agent'

const buildInviteLink = (code: string): string => {
  if (typeof window === 'undefined')
    return ''
  return `${window.location.origin}/signup?agent_code=${encodeURIComponent(code)}`
}

const AgentInvitationPage = () => {
  const { t } = useTranslation()
  const { data, isLoading } = useAgentInvitations()
  const generate = useGenerateInvitation()
  const [activeCode, setActiveCode] = useState<string | null>(null)

  const codes = data?.data ?? []

  // Auto-select the most recent code (server returns newest-first).
  const displayedCode = activeCode ?? codes[0]?.invite_code ?? null
  const inviteLink = useMemo(
    () => (displayedCode ? buildInviteLink(displayedCode) : ''),
    [displayedCode],
  )

  const handleGenerate = () => {
    generate.mutate(undefined, {
      onSuccess: (resp) => {
        setActiveCode(resp.invite_code)
      },
      onError: (err) => {
        toast.error(String(err?.message ?? 'Failed'))
      },
    })
  }

  const handleCopy = (text: string) => {
    if (!text)
      return
    void navigator.clipboard.writeText(text)
    toast.success(t('agent:invitation.copied'))
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">
          {t('agent:invitation.title')}
        </h1>
        <p className="mt-2 text-sm text-text-tertiary">
          {t('agent:invitation.intro')}
        </p>
      </div>

      <button
        type="button"
        onClick={handleGenerate}
        disabled={generate.isPending}
        className="w-fit rounded-md bg-components-button-primary-bg px-4 py-2 text-sm font-medium text-components-button-primary-text shadow-xs disabled:opacity-50"
      >
        {generate.isPending
          ? t('agent:invitation.generateLoading')
          : t('agent:invitation.generate')}
      </button>

      {displayedCode && (
        <section className="grid gap-6 rounded-lg border border-divider-subtle bg-background-default p-6 md:grid-cols-[auto_1fr]">
          <div className="flex flex-col items-center gap-2">
            <QRCodeSVG value={inviteLink} size={160} />
            <span className="text-xs text-text-tertiary">
              {t('agent:invitation.qrLabel')}
            </span>
          </div>
          <div className="flex flex-col gap-3">
            <div>
              <span className="block text-xs text-text-tertiary">
                {t('agent:invitation.codeLabel')}
              </span>
              <div className="mt-1 flex items-center gap-2">
                <code className="font-mono text-sm text-text-primary">
                  {displayedCode}
                </code>
                <button
                  type="button"
                  onClick={() => handleCopy(displayedCode)}
                  className="rounded-md border border-components-button-secondary-border px-2 py-1 text-xs text-text-secondary hover:bg-state-base-hover"
                >
                  {t('agent:invitation.copy')}
                </button>
              </div>
            </div>
            <div>
              <span className="block text-xs text-text-tertiary">
                {t('agent:invitation.linkLabel')}
              </span>
              <div className="mt-1 flex items-center gap-2">
                <code className="text-xs break-all text-text-secondary">
                  {inviteLink}
                </code>
                <button
                  type="button"
                  onClick={() => handleCopy(inviteLink)}
                  className="shrink-0 rounded-md border border-components-button-secondary-border px-2 py-1 text-xs text-text-secondary hover:bg-state-base-hover"
                >
                  {t('agent:invitation.copy')}
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-medium text-text-secondary">
          {t('agent:invitation.history')}
        </h2>
        {isLoading
          ? (
              <div className="text-sm text-text-tertiary">Loading...</div>
            )
          : codes.length === 0
            ? (
                <div className="text-sm text-text-tertiary">
                  {t('agent:invitation.empty')}
                </div>
              )
            : (
                <ul className="flex flex-col gap-2">
                  {codes.map(c => (
                    <li
                      key={c.invite_code}
                      className="flex items-center justify-between rounded-md border border-divider-subtle bg-background-default px-3 py-2"
                    >
                      <code className="font-mono text-xs text-text-primary">
                        {c.invite_code}
                      </code>
                      <button
                        type="button"
                        onClick={() => setActiveCode(c.invite_code)}
                        className="text-xs text-text-accent hover:underline"
                      >
                        {t('agent:invitation.qrLabel')}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
      </section>
    </div>
  )
}

export default AgentInvitationPage
