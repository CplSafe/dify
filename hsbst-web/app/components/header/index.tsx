'use client'
import DifyLogo from '@/app/components/base/logo/dify-logo'
import WorkplaceSelector from '@/app/components/header/account-dropdown/workplace-selector'
import { DEFAULT_BRAND_NAME } from '@/config'
import { useGlobalPublicStore } from '@/context/global-public-context'
import { WorkspaceProvider } from '@/context/workspace-context-provider'
import useBreakpoints, { MediaType } from '@/hooks/use-breakpoints'
import Link from '@/next/link'
import AccountDropdown from './account-dropdown'
import AppNav from './app-nav'

const Header = () => {
  const media = useBreakpoints()
  const isMobile = media === MediaType.mobile
  const systemFeatures = useGlobalPublicStore(s => s.systemFeatures)
  const isBrandingEnabled = systemFeatures.branding.enabled

  const renderLogo = () => (
    <h1>
      <Link href="/apps" aria-label={isBrandingEnabled && systemFeatures.branding.application_title ? systemFeatures.branding.application_title : DEFAULT_BRAND_NAME} className="flex h-8 shrink-0 items-center justify-center overflow-hidden whitespace-nowrap px-0.5">
        {systemFeatures.branding.enabled && systemFeatures.branding.workspace_logo
          ? (
              <img
                src={systemFeatures.branding.workspace_logo}
                className="block h-[22px] w-auto object-contain"
                alt="logo"
              />
            )
          : <DifyLogo />}
      </Link>
    </h1>
  )

  if (isMobile) {
    return (
      <div className="">
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center">
            {renderLogo()}
            <div className="mx-1.5 shrink-0 font-light text-divider-deep">/</div>
            <WorkspaceProvider>
              <WorkplaceSelector />
            </WorkspaceProvider>
          </div>
          <div className="flex items-center">
            <AccountDropdown />
          </div>
        </div>
        <div className="my-1 flex items-center justify-center space-x-1">
          <AppNav />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-[56px] items-center">
      <div className="flex min-w-0 flex-1 items-center pl-3 pr-2 min-[1280px]:pr-3">
        {renderLogo()}
        <div className="mx-1.5 shrink-0 font-light text-divider-deep">/</div>
        <WorkspaceProvider>
          <WorkplaceSelector />
        </WorkspaceProvider>
      </div>
      <div className="flex items-center space-x-2">
        <AppNav />
      </div>
      <div className="flex min-w-0 flex-1 items-center justify-end pl-2 pr-3 min-[1280px]:pl-3">
        <AccountDropdown />
      </div>
    </div>
  )
}
export default Header
