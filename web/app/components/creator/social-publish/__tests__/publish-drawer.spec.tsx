import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as React from 'react'

import { PublishDrawer } from '../publish-drawer'

const {
  fetchSocialPublishAccounts,
  createSocialPublishTask,
  fetchSocialPublishTask,
} = vi.hoisted(() => ({
  fetchSocialPublishAccounts: vi.fn(),
  createSocialPublishTask: vi.fn(),
  fetchSocialPublishTask: vi.fn(),
}))

vi.mock('@/service/social-publish', () => ({
  fetchSocialPublishAccounts,
  createSocialPublishTask,
  fetchSocialPublishTask,
}))

// useTranslation must return a stable singleton or our useEffect deps drift
// every render — see the auth-qr-modal test for the same pattern.
const STABLE_T_RESULT = { t: (key: string) => key }
vi.mock('react-i18next', () => ({
  useTranslation: () => STABLE_T_RESULT,
}))

const ACTIVE_ACCOUNT = {
  id: 'acc-1',
  platform: 'douyin' as const,
  display_name: '小妹',
  avatar_url: null,
  status: 'active' as const,
  last_check_at: null,
  created_at: '2026-04-18T00:00:00',
}

beforeEach(() => {
  fetchSocialPublishAccounts.mockReset()
  createSocialPublishTask.mockReset()
  fetchSocialPublishTask.mockReset()
})

describe('PublishDrawer', () => {
  it('loads active accounts on open and pre-selects when only one is active', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({
      data: [ACTIVE_ACCOUNT, { ...ACTIVE_ACCOUNT, id: 'acc-x', status: 'expired' }],
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
    // Submit button starts enabled: title is pre-filled and the single
    // active account auto-selected.
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
    expect(await screen.findByText('publish.noActiveAccount')).toBeInTheDocument()
    const submit = screen.getByText('publish.submit').closest('button')!
    expect(submit.disabled).toBe(true)
  })

  it('submits the form and starts polling on success', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [ACTIVE_ACCOUNT] })
    createSocialPublishTask.mockResolvedValue({ task_id: 'task-1', status: 'queued' })
    fetchSocialPublishTask.mockResolvedValue({
      task: {
        id: 'task-1',
        account_id: 'acc-1',
        work_id: 'work-1',
        platform: 'douyin',
        status: 'success',
        result_url: 'https://x',
        error_code: null,
        error_message: null,
        created_at: '2026-04-18T00:00:00',
        updated_at: '2026-04-18T00:00:00',
      },
      result: { url: 'https://x', error_code: null, error_message: null },
    })

    const onPublishSuccess = vi.fn()
    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hello"
        onOpenChange={vi.fn()}
        onPublishSuccess={onPublishSuccess}
      />,
    )

    const submit = (await screen.findByText('publish.submit')).closest('button')!
    await waitFor(() => expect(submit.disabled).toBe(false))
    fireEvent.click(submit)

    await waitFor(() =>
      expect(createSocialPublishTask).toHaveBeenCalledWith(
        expect.objectContaining({
          account_id: 'acc-1',
          work_id: 'work-1',
          title: 'hello',
        }),
      ),
    )
    // Wait for the first poll + terminal handling.
    await waitFor(() => expect(onPublishSuccess).toHaveBeenCalled(), {
      timeout: 8_000,
    })
    expect(await screen.findByText('publish.success')).toBeInTheDocument()
  }, 10_000)

  it('surfaces the localized error code when the dispatch rejects', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [ACTIVE_ACCOUNT] })
    createSocialPublishTask.mockRejectedValue({ code: 'task_already_in_flight' })

    render(
      <PublishDrawer
        open
        workId="work-1"
        defaultTitle="hi"
        onOpenChange={vi.fn()}
      />,
    )

    const submit = (await screen.findByText('publish.submit')).closest('button')!
    await waitFor(() => expect(submit.disabled).toBe(false))
    fireEvent.click(submit)

    expect(
      await screen.findByText('auth.errors.task_already_in_flight'),
    ).toBeInTheDocument()
  })

  it('cancel button fires onOpenChange(false)', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [ACTIVE_ACCOUNT] })
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
