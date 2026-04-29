import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PromptDialog from '../prompt-dialog'

const mockMutateAsync = vi.hoisted(() => vi.fn())
const mockToastSuccess = vi.hoisted(() => vi.fn())

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key}:${Object.values(values).join('|')}` : key,
  }),
}))

vi.mock('@/service/use-asset-library', () => ({
  useCreatePromptAsset: () => ({
    isPending: false,
    mutateAsync: mockMutateAsync,
  }),
}))

vi.mock('@/app/components/base/ui/toast', () => ({
  toast: {
    success: mockToastSuccess,
  },
}))

const openDialog = () => {
  render(<PromptDialog onCreated={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: 'prompt.newButton' }))
}

describe('PromptDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should be closed initially and open from the trigger', () => {
    render(<PromptDialog onCreated={() => {}} />)

    expect(screen.queryByText('prompt.dialogTitle')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'prompt.newButton' }))

    expect(screen.getByText('prompt.dialogTitle')).toBeInTheDocument()
  })

  it('should show validation error when name is empty', () => {
    openDialog()

    fireEvent.click(screen.getByRole('button', { name: 'prompt.create' }))

    expect(screen.getByText('prompt.validation.nameRequired')).toBeInTheDocument()
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('should show validation error when content is empty', () => {
    openDialog()

    fireEvent.change(screen.getByLabelText('prompt.fields.name'), {
      target: { value: 'Title prompt' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'prompt.create' }))

    expect(screen.getByText('prompt.validation.contentRequired')).toBeInTheDocument()
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('should add and remove variables', () => {
    openDialog()

    fireEvent.click(screen.getByRole('button', { name: 'prompt.fields.addVariable' }))

    expect(screen.getByLabelText('prompt.variableFields.name')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'prompt.variableFields.remove' }))

    expect(screen.queryByLabelText('prompt.variableFields.name')).not.toBeInTheDocument()
  })

  it('should add and remove tags', () => {
    openDialog()

    fireEvent.change(screen.getByLabelText('prompt.fields.tags'), {
      target: { value: 'launch' },
    })
    fireEvent.keyDown(screen.getByLabelText('prompt.fields.tags'), {
      key: 'Enter',
    })

    expect(screen.getByText('launch')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'filters.removeTag:launch' }))

    expect(screen.queryByText('launch')).not.toBeInTheDocument()
  })

  it('should validate variable names before submit', () => {
    openDialog()

    fireEvent.change(screen.getByLabelText('prompt.fields.name'), {
      target: { value: 'Title prompt' },
    })
    fireEvent.change(screen.getByLabelText('prompt.fields.content'), {
      target: { value: 'Write a title' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'prompt.fields.addVariable' }))
    fireEvent.change(screen.getByLabelText('prompt.variableFields.name'), {
      target: { value: '1bad' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'prompt.create' }))

    expect(screen.getByText('prompt.validation.variableNameInvalid')).toBeInTheDocument()
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('should submit optional metadata and variable field edits', async () => {
    mockMutateAsync.mockResolvedValueOnce({})
    render(<PromptDialog onCreated={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'prompt.newButton' }))

    fireEvent.change(screen.getByLabelText('prompt.fields.name'), {
      target: { value: 'Title prompt' },
    })
    fireEvent.change(screen.getByLabelText('prompt.fields.content'), {
      target: { value: 'Write a title' },
    })
    fireEvent.change(screen.getByLabelText('prompt.fields.description'), {
      target: { value: 'Useful for campaigns' },
    })
    fireEvent.change(screen.getByLabelText('prompt.fields.category'), {
      target: { value: 'marketing' },
    })
    fireEvent.change(screen.getByLabelText('prompt.fields.tags'), {
      target: { value: 'launch' },
    })
    fireEvent.keyDown(screen.getByLabelText('prompt.fields.tags'), {
      key: 'Enter',
    })
    fireEvent.click(screen.getByRole('button', { name: 'prompt.fields.addVariable' }))
    fireEvent.change(screen.getByLabelText('prompt.variableFields.name'), {
      target: { value: 'count' },
    })
    fireEvent.change(screen.getByLabelText('prompt.variableFields.type'), {
      target: { value: 'number' },
    })
    fireEvent.change(screen.getByLabelText('prompt.variableFields.default'), {
      target: { value: '3' },
    })
    fireEvent.change(screen.getByLabelText('prompt.variableFields.description'), {
      target: { value: 'Item count' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'prompt.create' }))

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        name: 'Title prompt',
        content: 'Write a title',
        prompt_variables: [
          {
            name: 'count',
            type: 'number',
            default: '3',
            description: 'Item count',
          },
        ],
        description: 'Useful for campaigns',
        tags: ['launch'],
        category: 'marketing',
      })
    })
  })

  it('should submit payload, close dialog, and call onCreated', async () => {
    mockMutateAsync.mockResolvedValueOnce({})
    const onCreated = vi.fn()
    render(<PromptDialog onCreated={onCreated} />)
    fireEvent.click(screen.getByRole('button', { name: 'prompt.newButton' }))

    fireEvent.change(screen.getByLabelText('prompt.fields.name'), {
      target: { value: 'Title prompt' },
    })
    fireEvent.change(screen.getByLabelText('prompt.fields.content'), {
      target: { value: 'Write a title' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'prompt.fields.addVariable' }))
    fireEvent.change(screen.getByLabelText('prompt.variableFields.name'), {
      target: { value: 'product_name' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'prompt.create' }))

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        name: 'Title prompt',
        content: 'Write a title',
        prompt_variables: [
          {
            name: 'product_name',
            type: 'string',
            default: null,
            description: null,
          },
        ],
        description: null,
        tags: [],
        category: null,
      })
    })
    expect(onCreated).toHaveBeenCalledTimes(1)
    expect(mockToastSuccess).toHaveBeenCalledWith('detail.savedToast')
    await waitFor(() => {
      expect(screen.queryByText('prompt.dialogTitle')).not.toBeInTheDocument()
    })
  })

  it('should keep dialog open and show error when creation fails', async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error('invalid variables'))
    openDialog()

    fireEvent.change(screen.getByLabelText('prompt.fields.name'), {
      target: { value: 'Title prompt' },
    })
    fireEvent.change(screen.getByLabelText('prompt.fields.content'), {
      target: { value: 'Write a title' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'prompt.create' }))

    expect(await screen.findByText('errors.validationFailed:invalid variables')).toBeInTheDocument()
    expect(screen.getByText('prompt.dialogTitle')).toBeInTheDocument()
  })
})
