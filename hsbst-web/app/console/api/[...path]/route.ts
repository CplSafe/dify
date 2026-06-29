import { NextResponse } from 'next/server'

const REMOTE_API_ORIGIN = process.env.HSBST_API_ORIGIN || 'https://hsbstapi.ziyouqingchun.com'

const hostCookiePairs = [
  ['__Host-access_token', 'access_token'],
  ['__Host-refresh_token', 'refresh_token'],
  ['__Host-csrf_token', 'csrf_token'],
] as const

function rewriteSetCookieForLocalhost(cookie: string) {
  let nextCookie = cookie

  hostCookiePairs.forEach(([remoteName, localName]) => {
    nextCookie = nextCookie.replace(new RegExp(`^${remoteName}=`), `${localName}=`)
  })

  return nextCookie
    .replace(/;\s*Secure/gi, '')
    .replace(/;\s*Domain=[^;]+/gi, '')
}

function rewriteCookieForRemoteApi(cookie: string) {
  const parts = cookie
    .split(';')
    .map(part => part.trim())
    .filter(Boolean)

  const aliases = hostCookiePairs.flatMap(([remoteName, localName]) => {
    if (parts.some(part => part.startsWith(`${remoteName}=`)))
      return []

    const localCookie = parts.find(part => part.startsWith(`${localName}=`))
    return localCookie ? [localCookie.replace(`${localName}=`, `${remoteName}=`)] : []
  })

  return [...parts, ...aliases].join('; ')
}

async function proxyConsoleApi(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  const requestUrl = new URL(request.url)
  const targetUrl = new URL(`/console/api/${path.join('/')}${requestUrl.search}`, REMOTE_API_ORIGIN)
  const headers = new Headers(request.headers)
  const cookie = headers.get('cookie')

  headers.delete('host')
  if (cookie)
    headers.set('cookie', rewriteCookieForRemoteApi(cookie))

  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.arrayBuffer(),
    redirect: 'manual',
  })

  const responseHeaders = new Headers(response.headers)
  responseHeaders.delete('content-encoding')
  responseHeaders.delete('transfer-encoding')
  responseHeaders.delete('set-cookie')

  response.headers.getSetCookie?.().forEach((cookie) => {
    responseHeaders.append('set-cookie', rewriteSetCookieForLocalhost(cookie))
  })

  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  })
}

export const GET = proxyConsoleApi
export const POST = proxyConsoleApi
export const PUT = proxyConsoleApi
export const PATCH = proxyConsoleApi
export const DELETE = proxyConsoleApi
