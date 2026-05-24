import type { FC } from 'react'
import { useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { RiLoader2Line, RiMicLine } from '@remixicon/react'
import { useHoldToSpeak } from './use-hold-to-speak'
import { toast } from '@/app/components/base/ui/toast'
import { cn } from '@/utils/classnames'

type HoldToSpeakButtonProps = {
  onConverted: (text: string) => void
  disabled?: boolean
}

const formatDuration = (seconds: number): string => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

/**
 * WeChat-style "hold to talk" bar. Press (mouse or touch) to record, release to
 * convert speech to text (filled into the input). Slide up while holding to cancel.
 */
const HoldToSpeakButton: FC<HoldToSpeakButtonProps> = ({ onConverted, disabled }) => {
  const { t } = useTranslation()
  const pressOriginYRef = useRef<number | null>(null)
  const { state, willCancel, duration, start, stop, updateCancelHint } = useHoldToSpeak({
    onConverted,
    onError: () => toast.error(t('voiceInput.notAllow', { ns: 'common' })),
  })

  const isRecording = state === 'recording'
  const isConverting = state === 'converting'

  const handlePressStart = useCallback((clientY: number) => {
    if (disabled || state !== 'idle')
      return
    pressOriginYRef.current = clientY
    void start()
  }, [disabled, state, start])

  const handlePressMove = useCallback((clientY: number) => {
    if (!isRecording || pressOriginYRef.current === null)
      return
    updateCancelHint(pressOriginYRef.current - clientY)
  }, [isRecording, updateCancelHint])

  const handlePressEnd = useCallback(() => {
    if (!isRecording)
      return
    void stop(willCancel)
    pressOriginYRef.current = null
  }, [isRecording, stop, willCancel])

  const label = isConverting
    ? t('voiceInput.converting', { ns: 'common' })
    : isRecording
      ? (willCancel ? t('voiceInput.releaseToCancel', { ns: 'common' }) : t('voiceInput.releaseToConvert', { ns: 'common' }))
      : t('voiceInput.holdToSpeak', { ns: 'common' })

  return (
    <button
      type="button"
      disabled={disabled || isConverting}
      className={cn(
        'flex h-9 w-full select-none items-center justify-center gap-1 rounded-lg text-sm font-medium transition-colors',
        'touch-none', // prevent scroll/zoom while holding on touch devices
        isRecording
          ? (willCancel ? 'bg-red-100 text-red-600' : 'bg-primary-100 text-primary-700')
          : 'bg-components-button-tertiary-bg text-text-secondary hover:bg-components-button-tertiary-bg-hover',
        (disabled || isConverting) && 'cursor-not-allowed opacity-60',
      )}
      onMouseDown={e => handlePressStart(e.clientY)}
      onMouseMove={e => handlePressMove(e.clientY)}
      onMouseUp={handlePressEnd}
      onMouseLeave={handlePressEnd}
      onTouchStart={e => handlePressStart(e.touches[0]?.clientY ?? 0)}
      onTouchMove={e => handlePressMove(e.touches[0]?.clientY ?? 0)}
      onTouchEnd={handlePressEnd}
      onContextMenu={e => e.preventDefault()}
      data-testid="hold-to-speak-button"
    >
      {isConverting
        ? <RiLoader2Line className="h-4 w-4 animate-spin" />
        : <RiMicLine className="h-4 w-4" />}
      <span>{label}</span>
      {isRecording && <span className="ml-1 tabular-nums">{formatDuration(duration)}</span>}
    </button>
  )
}

export default HoldToSpeakButton
