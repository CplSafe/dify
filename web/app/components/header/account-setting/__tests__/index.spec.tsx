import type { AccountSettingTab } from '../constants'
import type { AppContextValue } from '@/context/app-context'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { useAppContext } from '@/context/app-context'
import {
  baseProviderContextValue,
  useProviderContext,
} from '@/context/provider-context'
import useBreakpoints, { MediaType } from '@/hooks/use-breakpoints'
import { ACCOUNT_SETTING_TAB } from '../constants'
import AccountSetting from '../index'

vi.mock('@/context/provider-context', async (importOriginal) => {
  const actual
    = await importOriginal<typeof import('@/context/provider-context')>()
  return {
    ...actual,
    useProviderContext: vi.fn(),
  }
})

vi.mock('@/context/app-context', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/context/app-context')>()
  return {
    ...actual,
    useAppContext: vi.fn(),
  }
})

vi.mock('@/next/navigation', () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  })),
  usePathname: vi.fn(() => '/'),
  useParams: vi.fn(() => ({})),
  useSearchParams: vi.fn(() => ({ get: vi.fn() })),
}))

vi.mock('@/hooks/use-breakpoints', () => ({
  MediaType: {
    mobile: 'mobile',
    tablet: 'tablet',
    pc: 'pc',
  },
  default: vi.fn(),
}))

vi.mock(
  '@/app/components/header/account-setting/model-provider-page/hooks',
  () => ({
    useDefaultModel: vi.fn(() => ({ data: null, isLoading: false })),
    useUpdateDefaultModel: vi.fn(() => ({ trigger: vi.fn() })),
    useUpdateModelList: vi.fn(() => vi.fn()),
    useInvalidateDefaultModel: vi.fn(() => vi.fn()),
    useModelList: vi.fn(() => ({ data: [], isLoading: false })),
    useSystemDefaultModelAndModelList: vi.fn(() => [null, vi.fn()]),
  }),
)

vi.mock(
  '@/app/components/header/account-setting/model-provider-page/atoms',
  () => ({
    useResetModelProviderListExpanded: () => vi.fn(),
  }),
)

vi.mock('@/service/use-datasource', () => ({
  useGetDataSourceListAuth: vi.fn(() => ({ data: { result: [] } })),
}))

vi.mock('@/service/use-common', () => ({
  useApiBasedExtensions: vi.fn(() => ({ data: [], isPending: false })),
  useMembers: vi.fn(() => ({ data: { accounts: [] }, refetch: vi.fn() })),
  useProviderContext: vi.fn(),
}))

const baseAppContextValue: AppContextValue = {
  userProfile: {
    id: '1',
    name: 'Test User',
    email: 'test@example.com',
    avatar: '',
    avatar_url: '',
    is_password_set: false,
  },
  mutateUserProfile: vi.fn(),
  currentWorkspace: {
    id: '1',
    name: 'Workspace',
    plan: '',
    status: '',
    created_at: 0,
    role: 'owner',
    providers: [],
    trial_credits: 0,
    trial_credits_used: 0,
    next_credit_reset_date: 0,
  },
  isCurrentWorkspaceManager: true,
  isCurrentWorkspaceOwner: true,
  isCurrentWorkspaceEditor: true,
  isCurrentWorkspaceDatasetOperator: false,
  isSystemAdmin: false,
  mutateCurrentWorkspace: vi.fn(),
  langGeniusVersionInfo: {
    current_env: 'testing',
    current_version: '0.1.0',
    latest_version: '0.1.0',
    release_date: '',
    release_notes: '',
    version: '0.1.0',
    can_auto_update: false,
  },
  useSelector: vi.fn(),
  isLoadingCurrentWorkspace: false,
  isValidatingCurrentWorkspace: false,
}

describe('AccountSetting', () => {
  const mockOnCancel = vi.fn()
  const mockOnTabChange = vi.fn()
  const renderAccountSetting = (props?: {
    initialTab?: AccountSettingTab
    onCancel?: () => void
    onTabChange?: (tab: AccountSettingTab) => void
  }) => {
    const {
      initialTab = ACCOUNT_SETTING_TAB.MEMBERS,
      onCancel = mockOnCancel,
      onTabChange = mockOnTabChange,
    } = props ?? {}

    const StatefulAccountSetting = () => {
      const [activeTab, setActiveTab] = useState<AccountSettingTab>(initialTab)

      return (
        <AccountSetting
          onCancelAction={onCancel}
          activeTab={activeTab}
          onTabChangeAction={(tab) => {
            setActiveTab(tab)
            onTabChange(tab)
          }}
        />
      )
    }

    return render(
      <QueryClientProvider client={new QueryClient()}>
        <StatefulAccountSetting />
      </QueryClientProvider>,
    )
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useProviderContext).mockReturnValue({
      ...baseProviderContextValue,
      enableBilling: true,
      enableReplaceWebAppLogo: true,
    })
    vi.mocked(useAppContext).mockReturnValue(baseAppContextValue)
    vi.mocked(useBreakpoints).mockReturnValue(MediaType.pc)
  })

  describe('Rendering', () => {
    it('should render the sidebar with correct menu items', () => {
      renderAccountSetting()

      expect(
        screen.getByText('common.userProfile.settings'),
      ).toBeInTheDocument()
      expect(screen.getByText('common.settings.provider')).toBeInTheDocument()
      expect(
        screen.getAllByText('common.settings.members').length,
      ).toBeGreaterThan(0)
      expect(screen.getByText('common.settings.billing')).toBeInTheDocument()
      expect(
        screen.getByText('common.settings.dataSource'),
      ).toBeInTheDocument()
      expect(
        screen.getByText('common.settings.apiBasedExtension'),
      ).toBeInTheDocument()
      expect(screen.getByText('custom.custom')).toBeInTheDocument()
      expect(
        screen.getAllByText('common.settings.language').length,
      ).toBeGreaterThan(0)
    })

    it('should respect the initial tab', () => {
      renderAccountSetting({ initialTab: ACCOUNT_SETTING_TAB.DATA_SOURCE })

      // One in sidebar, one in header
      expect(
        screen.getAllByText('common.settings.dataSource').length,
      ).toBeGreaterThan(1)
    })

    it('should hide sidebar labels on mobile', () => {
      vi.mocked(useBreakpoints).mockReturnValue(MediaType.mobile)

      renderAccountSetting()

      expect(
        screen.queryByText('common.settings.provider'),
      ).not.toBeInTheDocument()
    })

    it('should filter items for dataset operator', () => {
      vi.mocked(useAppContext).mockReturnValue({
        ...baseAppContextValue,
        isCurrentWorkspaceDatasetOperator: true,
      })

      renderAccountSetting()

      expect(
        screen.queryByText('common.settings.provider'),
      ).not.toBeInTheDocument()
      expect(
        screen.queryByText('common.settings.members'),
      ).not.toBeInTheDocument()
      expect(screen.getByText('common.settings.language')).toBeInTheDocument()
    })

    it('should hide billing and custom tabs when disabled', () => {
      vi.mocked(useProviderContext).mockReturnValue({
        ...baseProviderContextValue,
        enableBilling: false,
        enableReplaceWebAppLogo: false,
      })

      renderAccountSetting()

      expect(
        screen.queryByText('common.settings.billing'),
      ).not.toBeInTheDocument()
      expect(screen.queryByText('custom.custom')).not.toBeInTheDocument()
    })
  })

  describe('Tab Navigation', () => {
    it('should change active tab when clicking on menu item', () => {
      renderAccountSetting({ onTabChange: mockOnTabChange })

      fireEvent.click(screen.getByText('common.settings.provider'))

      expect(mockOnTabChange).toHaveBeenCalledWith(
        ACCOUNT_SETTING_TAB.PROVIDER,
      )
      expect(
        screen.getByText('common.modelProvider.models'),
      ).toBeInTheDocument()
    })

    it('should navigate through various tabs and show correct details', () => {
      renderAccountSetting()

      fireEvent.click(screen.getByText('common.settings.billing'))
      expect(
        screen.getAllByText('common.settings.billing').length,
      ).toBeGreaterThan(1)

      fireEvent.click(screen.getByText('common.settings.dataSource'))
      expect(
        screen.getAllByText('common.settings.dataSource').length,
      ).toBeGreaterThan(1)

      fireEvent.click(screen.getByText('common.settings.apiBasedExtension'))
      expect(
        screen.getAllByText('common.settings.apiBasedExtension').length,
      ).toBeGreaterThan(1)

      fireEvent.click(screen.getByText('custom.custom'))
      expect(screen.getAllByText('custom.custom').length).toBeGreaterThan(1)

      fireEvent.click(screen.getAllByText('common.settings.language')[0])
      expect(
        screen.getAllByText('common.settings.language').length,
      ).toBeGreaterThan(1)

      fireEvent.click(screen.getAllByText('common.settings.members')[0])
      expect(
        screen.getAllByText('common.settings.members').length,
      ).toBeGreaterThan(1)
    })
  })

  describe('Interactions', () => {
    it('should call onCancel when clicking close button', () => {
      renderAccountSetting()
      const closeButton = screen
        .getByRole('dialog')
        .querySelector('.i-ri-close-line')
        ?.closest('button')
      expect(closeButton).not.toBeNull()
      fireEvent.click(closeButton!)

      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('should call onCancel when pressing Escape key', () => {
      renderAccountSetting()
      fireEvent.keyDown(document, { key: 'Escape' })

      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('should update search value in provider tab', () => {
      renderAccountSetting({ initialTab: ACCOUNT_SETTING_TAB.PROVIDER })

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'test-search' } })

      expect(input).toHaveValue('test-search')
      expect(
        screen.getByText('common.modelProvider.models'),
      ).toBeInTheDocument()
    })

    it('should handle scroll event in panel', () => {
      renderAccountSetting()
      const scrollContainer = screen
        .getByRole('dialog')
        .querySelector('.overscroll-contain')

      expect(scrollContainer).toBeInTheDocument()
      fireEvent.scroll(scrollContainer!, { target: { scrollTop: 100 } })
      expect(scrollContainer).toHaveClass('overscroll-contain')
      fireEvent.scroll(scrollContainer!, { target: { scrollTop: 0 } })
    })
  })
})
