/**
 * Resolves the home route after login based on the user's role.
 * System admins go to /apps; regular users go to /creator.
 */
export async function resolveHomeRoute(): Promise<string> {
  try {
    const res = await fetch('/console/api/account/profile', { credentials: 'include' })
    if (res.ok) {
      const data = await res.json()
      return data?.is_system_admin ? '/apps' : '/creator'
    }
  }
  catch {}
  return '/apps'
}
