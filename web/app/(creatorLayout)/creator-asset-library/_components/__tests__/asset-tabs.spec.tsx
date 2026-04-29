import type { TabValue } from '../asset-tabs'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AssetTabs from '../asset-tabs'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('AssetTabs', () => {
  it('should render all asset tabs', () => {
    render(<AssetTabs value="all" onChange={() => {}} />)

    expect(screen.getAllByRole('tab')).toHaveLength(5)
    ;['tabs.all', 'tabs.image', 'tabs.video', 'tabs.audio', 'tabs.prompt'].forEach((key) => {
      expect(screen.getByRole('tab', { name: key })).toBeInTheDocument()
    })
  })

  it('should mark the active tab', () => {
    render(<AssetTabs value="image" onChange={() => {}} />)

    expect(screen.getByRole('tab', { name: 'tabs.image' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByRole('tab', { name: 'tabs.all' })).toHaveAttribute(
      'aria-selected',
      'false',
    )
  })

  it('should call onChange when a tab is clicked', () => {
    const onChange = vi.fn()
    render(<AssetTabs value="all" onChange={onChange} />)

    fireEvent.click(screen.getByRole('tab', { name: 'tabs.video' }))

    expect(onChange).toHaveBeenCalledWith('video' satisfies TabValue)
  })
})
