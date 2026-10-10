import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
      if (url.endsWith('/trend')) {
        return Promise.resolve({
          data: [{ date: '2026-10-01', town: '赫山街道', conversation_count: 3 }],
          villages: [
            { date: '2026-10-01', town: '赫山街道', village: '洪家村社区', conversation_count: 2 },
            { date: '2026-10-01', town: '龙光桥街道', village: '天成垸村', conversation_count: 1 },
          ],
        })
      }
      return Promise.resolve({
        data: [
          { town: '赫山街道', conversation_count: 3, user_count: 2 },
          { town: '龙光桥街道', conversation_count: 1, user_count: 1 },
        ],
        villages: [
          { town: '赫山街道', village: '洪家村社区', conversation_count: 2, user_count: 1 },
          { town: '龙光桥街道', village: '天成垸村', conversation_count: 1, user_count: 1 },
        ],
        unspecified_count: 0,
        unspecified_user_count: 0,
      })
    })
  })

  it('should load aggregate data from anonymous WebApp endpoints', async () => {
    renderTownStats()

    expect(await screen.findByRole('heading', { name: '各乡镇使用情况' })).toBeInTheDocument()
    await waitFor(() => {
      expect(getPublic).toHaveBeenCalledWith('/town-statistics/distribution', expect.any(Object))
      expect(getPublic).toHaveBeenCalledWith('/town-statistics/trend', expect.any(Object))
    })
    expect(screen.getByText('区域明细')).toBeInTheDocument()
    expect(screen.getByText('洪家村社区')).toBeInTheDocument()
  })

  it('should switch statistic levels and filter village rows', async () => {
    renderTownStats()

    expect(await screen.findByText('洪家村社区')).toBeInTheDocument()
    expect(screen.getByText('天成垸村')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('按乡镇/街道筛选'), { target: { value: '龙光桥街道' } })
    expect(screen.queryByText('洪家村社区')).not.toBeInTheDocument()
    expect(screen.getByText('天成垸村')).toBeInTheDocument()

    fireEvent.click(within(screen.getByLabelText('统计层级')).getByRole('button', { name: '乡镇/街道' }))
    expect(screen.getByRole('columnheader', { name: '环比' })).toBeInTheDocument()
    expect(screen.queryByLabelText('按乡镇/街道筛选')).not.toBeInTheDocument()
  })

  it('should switch the ranking chart to village level', async () => {
    renderTownStats()

    expect(await screen.findByText('区域排名')).toBeInTheDocument()
    const levelControl = screen.getByLabelText('排名统计层级')
    fireEvent.click(within(levelControl).getByRole('button', { name: '村/社区' }))

    expect(screen.getByLabelText('排名按乡镇/街道筛选')).toBeInTheDocument()
    expect(screen.getByText('全区村/社区会话量前 20 名')).toBeInTheDocument()
  })

  it('should switch the trend chart to village level', async () => {
    renderTownStats()

    expect(await screen.findByText('使用趋势')).toBeInTheDocument()
    const levelControl = screen.getByLabelText('趋势统计层级')
    fireEvent.click(within(levelControl).getByRole('button', { name: '村/社区' }))

    expect(screen.getByLabelText('趋势按乡镇/街道筛选')).toBeInTheDocument()
    expect(screen.getByText('会话量排名前 2 的村/社区')).toBeInTheDocument()
  })
})
