export const getRedirectionPath = (
  _isCurrentWorkspaceEditor: boolean,
  app: { id: string, [key: string]: unknown },
) => {
  return `/app/${app.id}/develop`
}

export const getRedirection = (
  isCurrentWorkspaceEditor: boolean,
  app: { id: string, [key: string]: unknown },
  redirectionFunc: (href: string) => void,
) => {
  const redirectionPath = getRedirectionPath(isCurrentWorkspaceEditor, app)
  redirectionFunc(redirectionPath)
}
