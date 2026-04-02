type PoweredByBrandProps = {
  webappBrandRemoved?: boolean
  workspaceLogo?: string
  webappLogo?: string
  imgKey: number
}

const PoweredByBrand = ({
  webappBrandRemoved,
  workspaceLogo: _workspaceLogo,
  webappLogo: _webappLogo,
  imgKey: _imgKey,
}: PoweredByBrandProps) => {
  if (webappBrandRemoved)
    return null

  return null
}

export default PoweredByBrand
