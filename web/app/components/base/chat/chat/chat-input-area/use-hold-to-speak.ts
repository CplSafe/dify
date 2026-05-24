import { useCallback, useRef, useState } from 'react'
import Recorder from 'js-audio-recorder'
import { useParams, usePathname } from 'next/navigation'
import { convertToMp3 } from '@/app/components/base/voice-input/utils'
import { AppSourceType, audioToText } from '@/service/share'

export type HoldToSpeakState = 'idle' | 'recording' | 'converting'

type UseHoldToSpeakParams = {
  onConverted: (text: string) => void
  onError?: () => void
}

type UseHoldToSpeakResult = {
  state: HoldToSpeakState
  /** true while the pointer has slid up past the cancel threshold */
  willCancel: boolean
  /** elapsed recording seconds */
  duration: number
  start: () => Promise<void>
  /** finish recording; cancel=true discards the audio without converting */
  stop: (cancel?: boolean) => Promise<void>
  /** update slide-up-to-cancel state based on vertical delta from the press origin */
  updateCancelHint: (movedUpPx: number) => void
}

const MAX_RECORD_SECONDS = 600
const SLIDE_UP_CANCEL_THRESHOLD_PX = 60

/**
 * Encapsulates WeChat-style "hold to talk": press to record, release to convert
 * the recorded audio to text (filled back into the input), or slide up to cancel.
 * Reuses the existing recorder, MP3 conversion and audio-to-text endpoint.
 */
export const useHoldToSpeak = ({ onConverted, onError }: UseHoldToSpeakParams): UseHoldToSpeakResult => {
  const recorderRef = useRef<Recorder | null>(null)
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [state, setState] = useState<HoldToSpeakState>('idle')
  const [willCancel, setWillCancel] = useState(false)
  const [duration, setDuration] = useState(0)
  const pathname = usePathname()
  const params = useParams()

  const resolveEndpoint = useCallback((): { url: string; isPublic: boolean } => {
    if (params.token)
      return { url: '/audio-to-text', isPublic: true }
    if (params.appId) {
      if (pathname.search('explore/installed') > -1)
        return { url: `/installed-apps/${params.appId}/audio-to-text`, isPublic: false }
      return { url: `/apps/${params.appId}/audio-to-text`, isPublic: false }
    }
    return { url: '/audio-to-text', isPublic: true }
  }, [params.token, params.appId, pathname])

  const clearDurationTimer = useCallback(() => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current)
      durationTimerRef.current = null
    }
  }, [])

  const start = useCallback(async () => {
    if (state !== 'idle')
      return
    const recorder = new Recorder({ sampleBits: 16, sampleRate: 16000, numChannels: 1, compiling: false })
    recorderRef.current = recorder
    try {
      await recorder.start()
      setWillCancel(false)
      setDuration(0)
      setState('recording')
      durationTimerRef.current = setInterval(() => {
        setDuration((prev) => {
          const next = prev + 1
          if (next >= MAX_RECORD_SECONDS)
            void stop(false)
          return next
        })
      }, 1000)
    }
    catch {
      recorderRef.current = null
      setState('idle')
      onError?.()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, onError])

  const stop = useCallback(async (cancel = false) => {
    const recorder = recorderRef.current
    if (!recorder || state !== 'recording')
      return
    clearDurationTimer()
    recorder.stop()

    if (cancel) {
      recorderRef.current = null
      setState('idle')
      setWillCancel(false)
      return
    }

    setState('converting')
    try {
      const mp3Blob = convertToMp3(recorder)
      const mp3File = new File([mp3Blob], 'temp.mp3', { type: 'audio/mp3' })
      const formData = new FormData()
      formData.append('file', mp3File)
      formData.append('word_timestamps', 'disabled')
      const { url, isPublic } = resolveEndpoint()
      const res = await audioToText(url, isPublic ? AppSourceType.webApp : AppSourceType.installedApp, formData)
      onConverted(res.text)
    }
    catch {
      onError?.()
    }
    finally {
      recorderRef.current = null
      setState('idle')
      setWillCancel(false)
    }
  }, [state, clearDurationTimer, resolveEndpoint, onConverted, onError])

  const updateCancelHint = useCallback((movedUpPx: number) => {
    setWillCancel(movedUpPx >= SLIDE_UP_CANCEL_THRESHOLD_PX)
  }, [])

  return { state, willCancel, duration, start, stop, updateCancelHint }
}
