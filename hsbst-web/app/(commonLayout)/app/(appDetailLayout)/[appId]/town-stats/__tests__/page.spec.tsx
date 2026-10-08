import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { getPublic } from '@/service/base'
import { TownStats } from '../page'

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="chart" />,
}))

vi.mock('@/service/base', () => ({
  get: vi.fn(),
  getPublic: vi.fn(),
}))

vi.mock('@/next/navigation', () => ({
  useParams: () => ({}),
}))

const renderTownStats = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <TownStats source="public" />
    </QueryClientProvider>,
  )
}

describe('TownStats public source', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getPublic).mockImplementation((url) => {
      if (url.endsWith('/trend'))
        return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [], unspecified_count: 0, unspecified_user_count: 0 })
    })
  })

  it('should load aggregate data from anonymous WebApp endpoints', async () => {
    renderTownStats()

    expect(await screen.findByRole('heading', { name: '各乡镇使用情况' })).toBeInTheDocument()
    await waitFor(() => {
      expect(getPublic).toHaveBeenCalledWith('/town-statistics/distribution', expect.any(Object))
      expect(getPublic).toHaveBeenCalledWith('/town-statistics/trend', expect.any(Object))
    })
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })
})
