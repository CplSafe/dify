import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as React from 'react'

import { PublishDrawer } from '../publish-drawer'

const {
  fetchSocialPublishAccounts,
  createSocialPublishTask,
  createSocialPublishTasksBatch,
  fetchSocialPublishTask,
} = vi.hoisted(() => ({
  fetchSocialPublishAccounts: vi.fn(),
  createSocialPublishTask: vi.fn(),
  createSocialPublishTasksBatch: vi.fn(),
  fetchSocialPublishTask: vi.fn(),
}))

vi.mock('@/service/social-publish', () => ({
  fetchSocialPublishAccounts,
  createSocialPublishTask,
  createSocialPublishTasksBatch,
  fetchSocialPublishTask,
}))

// useTranslation must return a stable singleton or our useEffect deps drift
// every render — see the auth-qr-modal test for the same pattern.
const STABLE_T_RESULT = {
  t: (key: string, defaultOrOpts?: unknown) => {
    if (
      defaultOrOpts !== null
      && typeof defaultOrOpts === 'object'
      && !Array.isArray(defaultOrOpts)
    ) {
      // Naive interpolation so location labels don't lose their
      // {{platform}} / {{name}} placeholders in test assertions.
      let out = key
      for (const [k, v] of Object.entries(
        defaultOrOpts as Record<string, unknown>,
      ))
        out = `${out}|${k}=${String(v)}`
      return out
    }
    return key
  },
}
vi.mock('react-i18next', () => ({
  useTranslation: () => STABLE_T_RESULT,
}))

const DOUYIN_ACCOUNT = {
  id: 'acc-dy',
  platform: 'douyin' as const,
  display_name: '抖小妹',
  avatar_url: null,
  status: 'active' as const,
  last_check_at: null,
  created_at: '2026-04-18T00:00:00',
}

const XHS_ACCOUNT = {
  id: 'acc-xhs',
  platform: 'xhs' as const,
  display_name: '小红薯',
  avatar_url: null,
  status: 'active' as const,
  last_check_at: null,
  created_at: '2026-04-18T00:00:00',
}

beforeEach(() => {
  fetchSocialPublishAccounts.mockReset()
  createSocialPublishTask.mockReset()
  createSocialPublishTasksBatch.mockReset()
  fetchSocialPublishTask.mockReset()
})

describe('PublishDrawer', () => {
  it('loads active accounts for every supported platform on open', async () => {
    fetchSocialPublishAccounts.mockImplementation(async (platform: string) => {
      if (platform === 'douyin')
        return { data: [DOUYIN_ACCOUNT] }
      if (platform === 'xhs')
        return { data: [XHS_ACCOUNT] }
      return { data: [] }
    })

    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hi"
        onOpenChange={vi.fn()}
      />,
    )

    expect(await screen.findByText('publish.title')).toBeInTheDocument()
    await waitFor(() =>
      expect(fetchSocialPublishAccounts).toHaveBeenCalledWith('douyin'),
    )
    await waitFor(() =>
      expect(fetchSocialPublishAccounts).toHaveBeenCalledWith('xhs'),
    )
    // Both accounts render as toggleable chips.
    expect(
      await screen.findByTestId('account-chip-acc-dy'),
    ).toBeInTheDocument()
    expect(
      await screen.findByTestId('account-chip-acc-xhs'),
    ).toBeInTheDocument()
  })

  it('auto-selects the only active account across platforms', async () => {
    fetchSocialPublishAccounts.mockImplementation(async (platform: string) => {
      if (platform === 'douyin')
        return { data: [DOUYIN_ACCOUNT] }
      return { data: [] }
    })

    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hi"
        onOpenChange={vi.fn()}
      />,
    )
    const chip = await screen.findByTestId('account-chip-acc-dy')
    await waitFor(() => expect(chip.getAttribute('aria-pressed')).toBe('true'))
    // Submit button enabled because the chip is auto-selected and title prefilled.
    const submit = screen.getByText('publish.submit').closest('button')!
    await waitFor(() => expect(submit.disabled).toBe(false))
  })

  it('shows the no-active-account hint and disables submit when none returned', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [] })
    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hi"
        onOpenChange={vi.fn()}
      />,
    )
    expect(
      await screen.findByText('publish.noActiveAccount'),
    ).toBeInTheDocument()
    const submit = screen.getByText('publish.submit').closest('button')!
    expect(submit.disabled).toBe(true)
  })

  it('uses the single-task endpoint when only one account is selected', async () => {
    fetchSocialPublishAccounts.mockImplementation(async (platform: string) => {
      if (platform === 'douyin')
        return { data: [DOUYIN_ACCOUNT] }
      if (platform === 'xhs')
        return { data: [XHS_ACCOUNT] }
      return { data: [] }
    })
    createSocialPublishTask.mockResolvedValue({
      task_id: 'task-1',
      status: 'queued',
    })
    fetchSocialPublishTask.mockResolvedValue({
      task: {
        id: 'task-1',
        account_id: 'acc-xhs',
        work_id: 'work-1',
        platform: 'xhs',
        status: 'success',
        result_url: 'https://x',
        error_code: null,
        error_message: null,
        created_at: '2026-04-18T00:00:00',
        updated_at: '2026-04-18T00:00:00',
      },
      result: { url: 'https://x', error_code: null, error_message: null },
    })

    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hello"
        onOpenChange={vi.fn()}
      />,
    )

    // Two active accounts → none auto-selected. Pick xhs, fill location.
    const xhsChip = await screen.findByTestId('account-chip-acc-xhs')
    fireEvent.click(xhsChip)
    const location = await screen.findByTestId('location-input-acc-xhs')
    fireEvent.change(location, { target: { value: 'Shanghai' } })

    const submit = screen.getByText('publish.submit').closest('button')!
    await waitFor(() => expect(submit.disabled).toBe(false))
    fireEvent.click(submit)

    await waitFor(() =>
      expect(createSocialPublishTask).toHaveBeenCalledWith(
        expect.objectContaining({
          account_id: 'acc-xhs',
          work_id: 'work-1',
          title: 'hello',
          platform_payload: { location: 'Shanghai' },
        }),
      ),
    )
    expect(createSocialPublishTasksBatch).not.toHaveBeenCalled()
  })

  it('uses the batch endpoint when multiple accounts are selected', async () => {
    fetchSocialPublishAccounts.mockImplementation(async (platform: string) => {
      if (platform === 'douyin')
        return { data: [DOUYIN_ACCOUNT] }
      if (platform === 'xhs')
        return { data: [XHS_ACCOUNT] }
      return { data: [] }
    })
    createSocialPublishTasksBatch.mockResolvedValue({
      results: [
        {
          account_id: 'acc-dy',
          success: true,
          task_id: 'task-dy',
          error_code: null,
          error_message: null,
        },
        {
          account_id: 'acc-xhs',
          success: false,
          task_id: null,
          error_code: 'sau_unreachable',
          error_message: 'timeout',
        },
      ],
    })

    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hello"
        onOpenChange={vi.fn()}
      />,
    )

    fireEvent.click(await screen.findByTestId('account-chip-acc-dy'))
    fireEvent.click(await screen.findByTestId('account-chip-acc-xhs'))
    fireEvent.change(await screen.findByTestId('location-input-acc-dy'), {
      target: { value: 'Beijing' },
    })

    const submit = screen.getByText('publish.submit').closest('button')!
    await waitFor(() => expect(submit.disabled).toBe(false))
    fireEvent.click(submit)

    await waitFor(() =>
      expect(createSocialPublishTasksBatch).toHaveBeenCalledWith(
        expect.objectContaining({
          work_id: 'work-1',
          title: 'hello',
          targets: [
            {
              account_id: 'acc-dy',
              platform_payload: { location: 'Beijing' },
            },
            { account_id: 'acc-xhs' },
          ],
        }),
      ),
    )
    expect(createSocialPublishTask).not.toHaveBeenCalled()

    // Per-target rows render in the partial state.
    expect(await screen.findByText('publish.partial')).toBeInTheDocument()
    expect(
      await screen.findByTestId('batch-result-acc-dy'),
    ).toBeInTheDocument()
    expect(
      await screen.findByTestId('batch-result-acc-xhs'),
    ).toBeInTheDocument()
  })

  it('surfaces the localized error code when the dispatch rejects', async () => {
    fetchSocialPublishAccounts.mockImplementation(async (platform: string) =>
      platform === 'douyin' ? { data: [DOUYIN_ACCOUNT] } : { data: [] },
    )
    createSocialPublishTask.mockRejectedValue({
      code: 'task_already_in_flight',
    })

    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hi"
        onOpenChange={vi.fn()}
      />,
    )

    const submit = (await screen.findByText('publish.submit')).closest(
      'button',
    )!
    await waitFor(() => expect(submit.disabled).toBe(false))
    fireEvent.click(submit)

    expect(
      await screen.findByText('auth.errors.task_already_in_flight'),
    ).toBeInTheDocument()
  })

  it('cancel button fires onOpenChange(false)', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [] })
    const onOpenChange = vi.fn()
    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hi"
        onOpenChange={onOpenChange}
      />,
    )
    fireEvent.click(await screen.findByText('publish.cancel'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
