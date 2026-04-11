'use client'

import type { ReactNode } from 'react'
import { useEffect } from 'react'
import Loading from '@/app/components/base/loading'
import { useAppContext } from '@/context/app-context'
import { usePathname, useRouter } from '@/next/navigation'

const datasetOperatorRedirectRoutes = ['/apps', '/app', '/explore', '/tools'] as const

// Routes that only system admins can access — regular users are redirected to the creator portal.
// Any route NOT in this allowlist will also redirect non-admins.
const CREATOR_ALLOWED_ROUTES = ['/creator', '/creator-marketplace', '/creator-works', '/creator/balance'] as const

const isPathUnderRoute = (pathname: string, route: string) => pathname === route || pathname.startsWith(`${route}/`)

export default function RoleRouteGuard({ children }: { children: ReactNode }) {
  const { isCurrentWorkspaceDatasetOperator, isLoadingCurrentWorkspace, isSystemAdmin } = useAppContext()
  const pathname = usePathname()
  const router = useRouter()

  // Dataset operators are redirected to /datasets
  const shouldGuardDatasetOperatorRoute = datasetOperatorRedirectRoutes.some(route => isPathUnderRoute(pathname, route))
  const shouldRedirectDatasetOperator = shouldGuardDatasetOperatorRoute && !isLoadingCurrentWorkspace && isCurrentWorkspaceDatasetOperator

  // Non-admin users: redirect to /creator unless already on an allowed route
  const isRegularUser = !isSystemAdmin && !isCurrentWorkspaceDatasetOperator
  const isOnCreatorAllowedRoute = CREATOR_ALLOWED_ROUTES.some(route => isPathUnderRoute(pathname, route))
  const shouldRedirectToCreator = isRegularUser && !isOnCreatorAllowedRoute && !isLoadingCurrentWorkspace

  useEffect(() => {
    if (shouldRedirectDatasetOperator)
      router.replace('/datasets')
  }, [shouldRedirectDatasetOperator, router])

  useEffect(() => {
    if (shouldRedirectToCreator)
      router.replace('/creator')
  }, [shouldRedirectToCreator, router])

  // Show loading while workspace info is being fetched to avoid permission flicker
  if (isLoadingCurrentWorkspace)
    return <Loading type="app" />

  if (shouldRedirectDatasetOperator || shouldRedirectToCreator)
    return null

  return <>{children}</>
}
